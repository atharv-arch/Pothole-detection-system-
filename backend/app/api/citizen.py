# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Citizen Verification Webhook (Twilio WhatsApp)
# Section 11: Inbound WhatsApp reply handling
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

import hashlib
import logging
from datetime import datetime

from fastapi import APIRouter, Form, Response
from sqlalchemy import text

from app.database import AsyncSessionLocal

logger = logging.getLogger("apis.citizen")

router = APIRouter(prefix="/api/citizen", tags=["Citizen"])


@router.post("/verify")
async def receive_whatsapp_reply(
    Body: str = Form(...),
    From: str = Form(...),
):
    """
    Twilio inbound WhatsApp webhook.
    Processes citizen repair verification responses.

    Reply codes:
        1 = Yes, fully fixed
        2 = No, still damaged
        3 = Not sure
    """
    phone = From.replace("whatsapp:", "")
    reply_code = Body.strip()

    if reply_code not in ("1", "2", "3"):
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

        # Insert verification
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

        # Tally responses
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

        # Act on tally
        if yes_count >= 3:
            # Check SSIM too
            ssim_result = await db.execute(
                text("SELECT ssim_score FROM potholes WHERE uuid = :uuid"),
                {"uuid": pothole_uuid},
            )
            ssim_row = ssim_result.fetchone()
            ssim_val = float(ssim_row._mapping["ssim_score"] or 0) if ssim_row else 0

            if ssim_val > 0.88:
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

        elif no_count >= 3:
            # Trigger escalation
            from app.services.escalation import check_tier1_escalations
            logger.info("Citizens report unrepaired: %s", pothole_uuid)

        await db.commit()

    return Response(
        content="<?xml version='1.0'?><Response></Response>",
        media_type="text/xml",
    )
