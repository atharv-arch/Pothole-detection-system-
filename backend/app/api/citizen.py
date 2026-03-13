# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Citizen & Social Audit API Router
# Section 11: WhatsApp webhook + Social Audit endpoints
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

import hashlib
import logging
from datetime import datetime

from fastapi import APIRouter, Form, Response, HTTPException
from sqlalchemy import text

from app.database import AsyncSessionLocal

logger = logging.getLogger("apis.citizen")

router = APIRouter(prefix="/api/citizen", tags=["Citizen & Social Audit"])


@router.post("/verify")
async def receive_whatsapp_reply(
    Body: str = Form(...),
    From: str = Form(...),
):
    """
    Twilio inbound WhatsApp webhook — Social Audit responses.

    Processes citizen repair verification responses as part of
    the Social Audit framework (dual-layer accountability).

    Reply codes:
        1 = Yes, fully repaired
        2 = No, still damaged
        3 = Partially fixed / Not sure
        4 = Road condition has worsened
    """
    phone = From.replace("whatsapp:", "")
    reply_code = Body.strip()

    if reply_code not in ("1", "2", "3", "4"):
        return Response(
            content="<?xml version='1.0'?><Response></Response>",
            media_type="text/xml",
        )

    phone_hash = hashlib.sha256(phone.encode()).hexdigest()

    async with AsyncSessionLocal() as db:
        # Find pending verification for this phone
        result = await db.execute(
            text("""
                SELECT p.uuid
                FROM potholes p
                JOIN complaints c ON p.uuid = c.pothole_uuid
                WHERE p.status IN ('complaint_filed', 'escalated_l2')
                  AND c.status = 'filed'
                LIMIT 1
            """)
        )
        row = result.fetchone()

        if not row:
            return Response(
                content="<?xml version='1.0'?><Response></Response>",
                media_type="text/xml",
            )

        pothole_uuid = row._mapping["uuid"]

        # Insert Social Audit response
        await db.execute(
            text("""
                INSERT INTO citizen_verifications
                (pothole_uuid, phone_hash, response, timestamp)
                VALUES (:uuid, :phone, :resp, :ts)
            """),
            {
                "uuid": pothole_uuid,
                "phone": phone_hash,
                "resp": reply_code,
                "ts": datetime.utcnow(),
            },
        )

        # Tally responses for Social Audit quorum
        tally = await db.execute(
            text("""
                SELECT response, COUNT(*) as cnt
                FROM citizen_verifications
                WHERE pothole_uuid = :uuid
                GROUP BY response
            """),
            {"uuid": pothole_uuid},
        )
        counts = {r._mapping["response"]: r._mapping["cnt"] for r in tally.fetchall()}

        yes_count = counts.get("1", 0)
        no_count = counts.get("2", 0)
        worsened_count = counts.get("4", 0)
        total = sum(counts.values())

        # Loop Closure: Combine AI (SSIM) + Social Audit verdict
        if total >= 3:  # Quorum met
            ssim_result = await db.execute(
                text("SELECT ssim_score FROM potholes WHERE uuid = :uuid"),
                {"uuid": pothole_uuid},
            )
            ssim_row = ssim_result.fetchone()
            ssim_val = float(ssim_row._mapping["ssim_score"] or 0) if ssim_row else 0

            if yes_count >= 3 and ssim_val > 0.88:
                # VERIFIED: Both AI and citizens confirm repair
                await db.execute(
                    text("""
                        UPDATE potholes
                        SET status = 'verified_repaired',
                            repair_verified = TRUE,
                            updated_at = NOW()
                        WHERE uuid = :uuid
                    """),
                    {"uuid": pothole_uuid},
                )
                logger.info(
                    "Loop closure VERIFIED: %s (ssim=%.4f, yes=%d)",
                    pothole_uuid, ssim_val, yes_count,
                )

            elif no_count >= 3 or worsened_count >= 2:
                # CONFIRMED_UNREPAIRED or WORSENED: Trigger escalation
                logger.info(
                    "Loop closure UNREPAIRED: %s (no=%d, worsened=%d)",
                    pothole_uuid, no_count, worsened_count,
                )
                # Trigger re-inspection and escalation
                from app.services.escalation import check_tier1_escalations
                logger.info("Social Audit triggers escalation for: %s", pothole_uuid)

            elif yes_count >= 2 and ssim_val <= 0.88:
                # DISPUTED: Citizens say yes but AI says no
                logger.info(
                    "Loop closure DISPUTED: %s (ssim=%.4f, yes=%d) — re-inspection needed",
                    pothole_uuid, ssim_val, yes_count,
                )

        await db.commit()

    return Response(
        content="<?xml version='1.0'?><Response></Response>",
        media_type="text/xml",
    )


@router.get("/social-audit/{pothole_uuid}")
async def get_social_audit_status(pothole_uuid: str):
    """
    Get the Social Audit status for a pothole.

    Returns citizen responses, audit score, and loop closure verdict.
    """
    async with AsyncSessionLocal() as db:
        # Get pothole info
        pothole_result = await db.execute(
            text("""
                SELECT uuid, highway_id, km_marker, severity,
                       status, ssim_score, repair_verified
                FROM potholes WHERE uuid = :uuid
            """),
            {"uuid": pothole_uuid},
        )
        pothole = pothole_result.fetchone()
        if not pothole:
            raise HTTPException(status_code=404, detail="Pothole not found")

        p = dict(pothole._mapping)

        # Get citizen responses
        responses = await db.execute(
            text("""
                SELECT response, COUNT(*) as cnt
                FROM citizen_verifications
                WHERE pothole_uuid = :uuid
                GROUP BY response
            """),
            {"uuid": pothole_uuid},
        )

        response_counts = {
            r._mapping["response"]: int(r._mapping["cnt"])
            for r in responses.fetchall()
        }

        total = sum(response_counts.values())
        repaired_count = response_counts.get("1", 0)
        not_repaired_count = response_counts.get("2", 0)
        partial_count = response_counts.get("3", 0)
        worsened_count = response_counts.get("4", 0)

        # Compute Social Audit Score
        scores = {"1": 100, "2": 0, "3": 30, "4": -20}
        raw_score = sum(
            scores.get(code, 0) * count
            for code, count in response_counts.items()
        )
        social_audit_score = max(0, min(100, raw_score / total)) if total > 0 else 0

        # Determine loop closure verdict
        ssim_val = float(p.get("ssim_score") or 0)
        ai_says_repaired = ssim_val > 0.88
        citizens_say_repaired = social_audit_score >= 50

        if total < 3:
            verdict = "pending_audit"
        elif ai_says_repaired and citizens_say_repaired:
            verdict = "verified"
        elif ai_says_repaired and not citizens_say_repaired:
            verdict = "disputed"
        elif not ai_says_repaired and not citizens_say_repaired:
            verdict = "confirmed_unrepaired"
        elif worsened_count >= 2:
            verdict = "worsened"
        else:
            verdict = "disputed"

        return {
            "pothole_uuid": pothole_uuid,
            "highway": f"{p.get('highway_id')} KM {p.get('km_marker')}",
            "current_status": p.get("status"),
            "ai_verification": {
                "ssim_score": ssim_val,
                "verdict": "REPAIRED" if ai_says_repaired else "UNREPAIRED",
            },
            "social_audit": {
                "total_responses": total,
                "quorum_met": total >= 3,
                "quorum_threshold": 3,
                "social_audit_score": round(social_audit_score, 1),
                "responses": {
                    "repaired": repaired_count,
                    "not_repaired": not_repaired_count,
                    "partial_unsure": partial_count,
                    "worsened": worsened_count,
                },
            },
            "loop_closure_verdict": verdict,
            "repair_verified": p.get("repair_verified", False),
        }
