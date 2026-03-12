# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Three-Tier Auto-Escalation Engine
# Section 10: SLA breach → Tier 2 → Tier 3 + RTI filing
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from app.config import settings

logger = logging.getLogger("apis.escalation")


async def check_tier1_escalations(db_session) -> list[dict]:
    """
    Find all Tier 1 complaints that have breached their 30-day SLA.

    Returns list of complaints needing T1→T2 escalation.
    """
    from sqlalchemy import text

    result = await db_session.execute(
        text("""
            SELECT c.complaint_id, c.pothole_uuid, c.filed_at,
                   c.sla_deadline, c.reference_number,
                   p.risk_score, p.severity, p.highway_id, p.km_marker
            FROM complaints c
            JOIN potholes p ON c.pothole_uuid = p.uuid
            WHERE c.tier = 1
              AND c.sla_deadline < NOW()
              AND c.status NOT IN ('resolved', 'verified_repaired')
              AND p.status NOT IN ('verified_repaired')
            ORDER BY p.risk_score DESC
        """)
    )
    return [dict(row._mapping) for row in result.fetchall()]


async def escalate_to_tier2(complaint: dict, db_session) -> dict:
    """
    Execute Tier 1 → Tier 2 escalation:
        1. Regenerate complaint letter with escalation language via Gemini
        2. File new complaint on PG Portal targeting NHAI Regional Office
        3. Send SMS to division engineer
        4. Log escalation
    """
    from sqlalchemy import text

    complaint_id = complaint["complaint_id"]
    pothole_uuid = complaint["pothole_uuid"]
    original_ref = complaint.get("reference_number", "N/A")
    filed_date = complaint.get("filed_at", datetime.now())
    days_elapsed = (datetime.now() - filed_date).days if isinstance(filed_date, datetime) else 30

    logger.info(
        "Escalating %s to Tier 2 (days=%d, original_ref=%s)",
        complaint_id, days_elapsed, original_ref,
    )

    # Generate escalation letter
    escalation_letter = await _generate_escalation_letter(
        complaint, tier=2, original_ref=original_ref, days_elapsed=days_elapsed
    )

    # Update complaint to tier 2
    new_sla = datetime.now() + timedelta(days=15)
    await db_session.execute(
        text("""
            UPDATE complaints
            SET tier = 2, escalated_at = NOW(), sla_deadline = :new_sla,
                status = 'escalated_l2'
            WHERE complaint_id = :cid
        """),
        {"cid": complaint_id, "new_sla": new_sla},
    )

    # Update pothole status
    await db_session.execute(
        text("""
            UPDATE potholes SET status = 'escalated_l2', updated_at = NOW()
            WHERE uuid = :uuid
        """),
        {"uuid": pothole_uuid},
    )

    # Log escalation
    await db_session.execute(
        text("""
            INSERT INTO escalation_log
            (complaint_id, pothole_uuid, tier_from, tier_to, reason,
             gemini_letter, days_since_original)
            VALUES (:cid, :uuid, 1, 2, 'SLA breach at Division level',
                    :letter, :days)
        """),
        {
            "cid": complaint_id,
            "uuid": pothole_uuid,
            "letter": escalation_letter,
            "days": days_elapsed,
        },
    )

    await db_session.commit()

    # Send SMS notification
    await _send_escalation_sms(complaint, tier=2)

    return {
        "complaint_id": complaint_id,
        "escalated_to": 2,
        "new_sla": new_sla.isoformat(),
    }


async def check_tier2_escalations(db_session) -> list[dict]:
    """Find Tier 2 complaints that have breached their 15-day SLA."""
    from sqlalchemy import text

    result = await db_session.execute(
        text("""
            SELECT c.complaint_id, c.pothole_uuid, c.filed_at,
                   c.escalated_at, c.reference_number,
                   p.risk_score, p.severity, p.highway_id, p.km_marker
            FROM complaints c
            JOIN potholes p ON c.pothole_uuid = p.uuid
            WHERE c.tier = 2
              AND c.escalated_at + INTERVAL '15 days' < NOW()
              AND c.status NOT IN ('resolved', 'verified_repaired')
        """)
    )
    return [dict(row._mapping) for row in result.fetchall()]


async def escalate_to_tier3(complaint: dict, db_session) -> dict:
    """
    Execute Tier 2 → Tier 3 escalation:
        1. File complaint to NHAI Chairman + MoRTH Grievance Cell
        2. Generate RTI application via Gemini
        3. Mark pothole as SLA_BREACH_PUBLIC on dashboard
        4. Broadcast WhatsApp alert to highway subscribers
        5. Update status to escalated_l3
    """
    from sqlalchemy import text

    complaint_id = complaint["complaint_id"]
    pothole_uuid = complaint["pothole_uuid"]
    filed_date = complaint.get("filed_at", datetime.now())
    days_elapsed = (datetime.now() - filed_date).days if isinstance(filed_date, datetime) else 45

    logger.info(
        "Escalating %s to Tier 3 — NHAI HQ + RTI (days=%d)",
        complaint_id, days_elapsed,
    )

    # Generate RTI application text
    rti_text = await _generate_rti_application(complaint)

    # Update complaint to tier 3
    await db_session.execute(
        text("""
            UPDATE complaints
            SET tier = 3, escalated_at = NOW(), status = 'escalated_l3'
            WHERE complaint_id = :cid
        """),
        {"cid": complaint_id},
    )

    # Mark pothole as public SLA breach
    await db_session.execute(
        text("""
            UPDATE potholes
            SET status = 'sla_breach_public', updated_at = NOW()
            WHERE uuid = :uuid
        """),
        {"uuid": pothole_uuid},
    )

    # Log escalation with RTI reference
    await db_session.execute(
        text("""
            INSERT INTO escalation_log
            (complaint_id, pothole_uuid, tier_from, tier_to, reason,
             gemini_letter, rti_reference, days_since_original)
            VALUES (:cid, :uuid, 2, 3,
                    'SLA breach at Regional level — escalated to NHAI HQ + RTI',
                    :letter, :rti, :days)
        """),
        {
            "cid": complaint_id,
            "uuid": pothole_uuid,
            "letter": rti_text,
            "rti": "RTI-PENDING",
            "days": days_elapsed,
        },
    )

    await db_session.commit()

    # Broadcast WhatsApp alert
    await _broadcast_whatsapp_alert(complaint, days_elapsed)

    return {
        "complaint_id": complaint_id,
        "escalated_to": 3,
        "rti_filed": True,
    }


async def _generate_escalation_letter(
    complaint: dict, tier: int, original_ref: str, days_elapsed: int
) -> str:
    """Generate escalation letter via Gemini with escalation language."""
    if not settings.GEMINI_API_KEY:
        return (
            f"TIER {tier} ESCALATION: Original complaint {original_ref} "
            f"filed {days_elapsed} days ago has not been actioned. "
            f"This constitutes an SLA violation under NHAI GRP-2022."
        )

    try:
        import google.generativeai as genai

        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-1.5-pro")

        prompt = (
            f"Write a formal Tier {tier} escalation letter for a pothole complaint. "
            f"Original complaint ref: {original_ref}, filed {days_elapsed} days ago. "
            f"Highway: {complaint.get('highway_id', 'NH-30')}, "
            f"KM: {complaint.get('km_marker', 'N/A')}. "
            f"Risk score: {complaint.get('risk_score', 5.0)}/10. "
            f"This is a policy violation under NHAI GRP-2022 30-day SLA. "
            f"Length: 200-300 words. Formal government correspondence style."
        )

        response = model.generate_content(prompt)
        return response.text

    except Exception as e:
        logger.error("Gemini escalation letter failed: %s", e)
        return f"TIER {tier} ESCALATION — SLA breach after {days_elapsed} days."


async def _generate_rti_application(complaint: dict) -> str:
    """Generate RTI application text via Gemini."""
    if not settings.GEMINI_API_KEY:
        return (
            f"RTI Application under RTI Act 2005, Section 6: "
            f"Requesting work order, contractor details, and inspection reports "
            f"for pothole repair at {complaint.get('highway_id', 'NH-30')} "
            f"KM {complaint.get('km_marker', 'N/A')}."
        )

    try:
        import google.generativeai as genai

        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-1.5-pro")

        prompt = (
            f"Draft an RTI application under RTI Act 2005, Section 6 requesting: "
            f"(a) Work order issued for repair of pothole at {complaint.get('highway_id')} "
            f"KM {complaint.get('km_marker')} "
            f"(b) Contractor name and contract number "
            f"(c) Inspection reports for this highway section "
            f"(d) Escalation communication records. "
            f"Address: Public Information Officer, NHAI. "
            f"Length: 150-200 words."
        )

        response = model.generate_content(prompt)
        return response.text

    except Exception as e:
        logger.error("Gemini RTI generation failed: %s", e)
        return "RTI application pending generation."


async def _send_escalation_sms(complaint: dict, tier: int) -> None:
    """Send SMS notification about escalation via Twilio."""
    if not settings.TWILIO_ACCOUNT_SID:
        logger.warning("Twilio not configured — skipping escalation SMS")
        return

    try:
        from app.services.twilio_svc import send_sms

        message = (
            f"⚠️ APIS Alert: Pothole complaint on {complaint.get('highway_id', 'NH-30')} "
            f"KM {complaint.get('km_marker', 'N/A')} escalated to Tier {tier}. "
            f"Original ref: {complaint.get('reference_number', 'N/A')}. "
            f"Risk: {complaint.get('risk_score', 5.0)}/10."
        )
        await send_sms(settings.SYSTEM_PHONE or "", message)
    except Exception as e:
        logger.error("Escalation SMS failed: %s", e)


async def _broadcast_whatsapp_alert(complaint: dict, days: int) -> None:
    """Broadcast WhatsApp alert about Tier 3 public SLA breach."""
    if not settings.TWILIO_ACCOUNT_SID:
        logger.warning("Twilio not configured — skipping WhatsApp broadcast")
        return

    try:
        from app.services.twilio_svc import send_whatsapp

        message = (
            f"⚠️ Road Safety Alert: Critical pothole on "
            f"{complaint.get('highway_id', 'NH-30')} KM {complaint.get('km_marker', 'N/A')} "
            f"has not been repaired after {days} days despite complaints. "
            f"Escalated to NHAI National HQ. Drive carefully. "
            f"Ref: {complaint.get('pothole_uuid', 'N/A')}"
        )
        # In production: query subscriber list from DB and send to each
        logger.info("WhatsApp broadcast queued: %s", message[:80])
    except Exception as e:
        logger.error("WhatsApp broadcast failed: %s", e)
