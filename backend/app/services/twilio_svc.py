# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Twilio WhatsApp & SMS Service
# Section 11: Social Audit polls, escalation alerts
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger("apis.twilio_svc")

_client = None


def _get_twilio_client():
    """Lazy-load Twilio client."""
    global _client
    if _client is not None:
        return _client

    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        raise RuntimeError("Twilio credentials not configured")

    from twilio.rest import Client

    _client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    return _client


async def send_whatsapp(to_phone: str, message: str) -> str | None:
    """
    Send a WhatsApp message via Twilio.

    Args:
        to_phone: recipient phone number (with country code)
        message: message body

    Returns:
        Twilio message SID or None on failure
    """
    if not settings.TWILIO_WHATSAPP_FROM:
        logger.warning("TWILIO_WHATSAPP_FROM not set")
        return None

    try:
        client = _get_twilio_client()
        msg = client.messages.create(
            body=message,
            from_=f"whatsapp:{settings.TWILIO_WHATSAPP_FROM}",
            to=f"whatsapp:{to_phone}",
        )
        logger.info("WhatsApp sent to %s: SID=%s", to_phone, msg.sid)
        return msg.sid
    except Exception as e:
        logger.error("WhatsApp send failed: %s", e)
        return None


async def send_sms(to_phone: str, message: str) -> str | None:
    """
    Send an SMS via Twilio.

    Returns Twilio message SID or None on failure.
    """
    if not settings.TWILIO_SMS_FROM:
        logger.warning("TWILIO_SMS_FROM not set")
        return None

    try:
        client = _get_twilio_client()
        msg = client.messages.create(
            body=message,
            from_=settings.TWILIO_SMS_FROM,
            to=to_phone,
        )
        logger.info("SMS sent to %s: SID=%s", to_phone, msg.sid)
        return msg.sid
    except Exception as e:
        logger.error("SMS send failed: %s", e)
        return None


async def send_social_audit_poll(
    pothole: dict, user_phone: str
) -> str | None:
    """
    Send a Social Audit verification poll via WhatsApp.

    Framed as an official government Social Audit — not a casual
    poll. This creates a double-layer accountability mechanism:
    AI verification + citizen ground-truth confirmation.
    """
    from app.services.social_audit import generate_social_audit_message

    msg_body = generate_social_audit_message(pothole)
    return await send_whatsapp(user_phone, msg_body)


async def send_escalation_alert(
    pothole: dict, tier: int, days_elapsed: int
) -> str | None:
    """Send an escalation alert via WhatsApp."""
    msg_body = (
        f"⚠️ APIS Escalation Alert — Tier {tier}\n\n"
        f"Pothole on {pothole.get('highway_id', 'NH-30')} "
        f"KM {pothole.get('km_marker', 'N/A')} has NOT been repaired "
        f"after {days_elapsed} days despite complaints.\n\n"
        f"Escalated to {'NHAI Regional Office' if tier == 2 else 'NHAI HQ + RTI'}.\n"
        f"Ref: {pothole.get('uuid', 'N/A')}"
    )
    return await send_whatsapp(
        settings.SYSTEM_PHONE or "", msg_body
    )
