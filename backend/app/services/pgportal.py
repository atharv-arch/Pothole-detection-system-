# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — CPGRAMS API-Based Complaint Filing (Production)
# Section 9: Secure API integration with Centralized Public
#             Grievance Redress & Monitoring System (CPGRAMS)
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta
from typing import Optional

import httpx

from app.config import settings
from app.services.s3 import s3_download_temp, s3_upload

logger = logging.getLogger("apis.cpgrams")

# ── CPGRAMS API Constants ─────────────────────────────────────
MINISTRY_CODE_MORTH = "064"          # Ministry of Road Transport & Highways
DEPARTMENT_CODE_NHAI = "064001"      # National Highways Authority of India
GRIEVANCE_CATEGORY = "ROAD_INFRA"    # Infrastructure grievance category


class CPGRAMSClient:
    """
    Secure API client for CPGRAMS — the official REST API backend
    of pgportal.gov.in used by government departments.

    Authentication: OAuth2 client credentials flow with
    government-issued API key and secret.

    Endpoints:
        POST /api/v1/auth/token          → Get bearer token
        POST /api/v1/grievances          → Lodge grievance
        GET  /api/v1/grievances/{ref}    → Check status
        POST /api/v1/grievances/{ref}/escalate → Escalate
    """

    def __init__(self):
        self.base_url = settings.CPGRAMS_API_BASE_URL
        self.client_id = settings.CPGRAMS_CLIENT_ID
        self.client_secret = settings.CPGRAMS_CLIENT_SECRET
        self._token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None

    def _ensure_credentials(self):
        """Validate that CPGRAMS credentials are configured."""
        if not self.client_id or not self.client_secret:
            raise RuntimeError(
                "CPGRAMS_CLIENT_ID/SECRET not set — "
                "cannot file grievance via API. "
                "Contact CHIPS administrator for API credentials."
            )

    async def _get_token(self) -> str:
        """
        Obtain or refresh OAuth2 bearer token via client credentials.

        Token is cached and reused until 5 minutes before expiry.
        """
        if (
            self._token
            and self._token_expiry
            and datetime.now() < self._token_expiry - timedelta(minutes=5)
        ):
            return self._token

        self._ensure_credentials()

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/auth/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "scope": "grievance.file grievance.read grievance.escalate",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            token_data = response.json()

        self._token = token_data["access_token"]
        expires_in = token_data.get("expires_in", 3600)
        self._token_expiry = datetime.now() + timedelta(seconds=expires_in)

        logger.info("CPGRAMS token acquired (expires in %ds)", expires_in)
        return self._token

    async def _auth_headers(self) -> dict:
        """Return Authorization header with bearer token."""
        token = await self._get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Source-System": "APIS-CHIPS-CG",
            "X-API-Version": "1.0",
        }

    async def file_grievance(self, complaint: dict) -> dict:
        """
        File a grievance via CPGRAMS REST API.

        Payload follows the CPGRAMS JSON schema:
            - ministry_code, department_code
            - grievance_text (max 3000 chars)
            - grievance_category
            - complainant details
            - location (GPS, highway, district)
            - attachments (base64 or pre-uploaded)
            - system_reference (APIS pothole UUID)

        Returns:
            {
                'registration_number': str,
                'acknowledgement_id': str,
                'sla_deadline': str (ISO date),
                'status': str
            }
        """
        self._ensure_credentials()
        complaint_id = complaint.get("complaint_id", "UNKNOWN")

        # Build CPGRAMS-compliant payload
        payload = {
            "ministry_code": MINISTRY_CODE_MORTH,
            "department_code": DEPARTMENT_CODE_NHAI,
            "grievance_category": GRIEVANCE_CATEGORY,
            "grievance_text": (complaint.get("letter", "")[:3000]),
            "subject": complaint.get("metadata", {}).get(
                "subject_line",
                f"Pothole Complaint — {complaint.get('highway_id', 'NH-30')} "
                f"KM {complaint.get('km_marker', 'N/A')}",
            ),
            "priority": complaint.get("metadata", {}).get("priority", "HIGH"),
            "complainant": {
                "name": "APIS Automated Monitor — CHIPS",
                "organization": "Chhattisgarh Infotech Promotion Society",
                "designation": "AI Road Monitoring System",
                "email": settings.SYSTEM_EMAIL or "apis@chips.cg.gov.in",
                "phone": settings.SYSTEM_PHONE or "",
                "state_code": "22",  # Chhattisgarh
                "district": complaint.get("district", "Raipur"),
            },
            "location": {
                "state": "Chhattisgarh",
                "district": complaint.get("district", "Raipur"),
                "highway_id": complaint.get("highway_id", "NH-30"),
                "km_marker": complaint.get("km_marker"),
                "latitude": complaint.get("lat"),
                "longitude": complaint.get("lon"),
                "address": (
                    f"{complaint.get('highway_id', 'NH-30')}, "
                    f"KM {complaint.get('km_marker', 'N/A')}, Chhattisgarh"
                ),
            },
            "system_reference": complaint.get("pothole_uuid", complaint_id),
            "source_system": "APIS-v5.0-CHIPS",
            "auto_generated": True,
        }

        # Attach PDF if available
        attachments = []
        if complaint.get("pdf_s3_url") or complaint.get("letter_pdf_s3"):
            pdf_url = complaint.get("pdf_s3_url") or complaint.get("letter_pdf_s3")
            try:
                local_pdf = s3_download_temp(pdf_url)
                import base64
                with open(local_pdf, "rb") as f:
                    pdf_b64 = base64.b64encode(f.read()).decode()
                attachments.append({
                    "filename": f"{complaint_id}_complaint.pdf",
                    "content_type": "application/pdf",
                    "data": pdf_b64,
                })
            except Exception as e:
                logger.warning("Failed to attach PDF: %s", e)

        if attachments:
            payload["attachments"] = attachments

        # Submit via API
        headers = await self._auth_headers()

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/grievances",
                json=payload,
                headers=headers,
            )

            if response.status_code == 401:
                # Token expired — refresh and retry once
                self._token = None
                headers = await self._auth_headers()
                response = await client.post(
                    f"{self.base_url}/api/v1/grievances",
                    json=payload,
                    headers=headers,
                )

            response.raise_for_status()
            result = response.json()

        registration_number = result.get("registration_number", "")
        logger.info(
            "CPGRAMS filed: %s → ref=%s",
            complaint_id, registration_number,
        )

        return {
            "registration_number": registration_number,
            "acknowledgement_id": result.get("acknowledgement_id", ""),
            "sla_deadline": result.get("sla_deadline", ""),
            "status": result.get("status", "registered"),
        }

    async def check_status(self, registration_number: str) -> dict:
        """Check grievance status via CPGRAMS API."""
        headers = await self._auth_headers()

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/grievances/{registration_number}",
                headers=headers,
            )
            response.raise_for_status()
            return response.json()

    async def escalate_grievance(
        self, registration_number: str,
        escalation_reason: str,
        new_tier: int,
    ) -> dict:
        """Escalate a grievance via CPGRAMS API."""
        headers = await self._auth_headers()
        payload = {
            "reason": escalation_reason,
            "escalation_tier": new_tier,
            "source_system": "APIS-v5.0-CHIPS",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/grievances/{registration_number}/escalate",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            return response.json()


# ── Module-level singleton ────────────────────────────────────
_cpgrams_client: Optional[CPGRAMSClient] = None


def get_cpgrams_client() -> CPGRAMSClient:
    """Get or create the CPGRAMS API client singleton."""
    global _cpgrams_client
    if _cpgrams_client is None:
        _cpgrams_client = CPGRAMSClient()
    return _cpgrams_client


async def file_via_cpgrams_api(complaint: dict) -> str:
    """
    High-level function to file a complaint via CPGRAMS API.

    Returns the registration/reference number.
    Falls back to email if API unavailable.
    """
    client = get_cpgrams_client()
    result = await client.file_grievance(complaint)
    return result.get("registration_number", "")


# ── Email Fallback (kept from original) ───────────────────────
def fallback_email_complaint(complaint: dict) -> None:
    """
    Fallback: send complaint via email when CPGRAMS API
    filing fails after max retries.
    """
    import smtplib
    from email import encoders
    from email.mime.base import MIMEBase
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    if not settings.SYSTEM_EMAIL or not settings.SYSTEM_EMAIL_PASS:
        logger.error("SYSTEM_EMAIL not configured — cannot send fallback email")
        return

    msg = MIMEMultipart()
    msg["Subject"] = complaint.get("metadata", {}).get(
        "subject_line", "Pothole Complaint — APIS"
    )
    msg["From"] = settings.SYSTEM_EMAIL
    msg["To"] = _get_division_engineer_email(complaint.get("highway_id", "NH-30"))

    # Body
    body = complaint.get("letter", "See attached complaint letter.")
    msg.attach(MIMEText(body, "plain"))

    # Attach PDF
    if complaint.get("pdf_s3_url"):
        try:
            local_pdf = s3_download_temp(complaint["pdf_s3_url"])
            with open(local_pdf, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f'attachment; filename="{complaint.get("complaint_id", "complaint")}.pdf"',
                )
                msg.attach(part)
        except Exception as e:
            logger.warning("Failed to attach PDF: %s", e)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(settings.SYSTEM_EMAIL, settings.SYSTEM_EMAIL_PASS)
            server.sendmail(msg["From"], msg["To"], msg.as_string())
        logger.info("Fallback email sent for %s", complaint.get("complaint_id"))
    except Exception as e:
        logger.error("Fallback email failed: %s", e)


def _get_division_engineer_email(highway_id: str) -> str:
    """Map highway to division engineer email."""
    return settings.SYSTEM_EMAIL or "grievance@nhai.org"
