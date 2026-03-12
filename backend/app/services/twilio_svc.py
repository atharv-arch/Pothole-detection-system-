# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Twilio WhatsApp & SMS Service
# Section 11: Citizen verification polls, escalation alerts
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


async def send_repair_verification_poll(
    pothole: dict, user_phone: str
) -> str | None:
    """
    Send a WhatsApp poll asking citizens to verify repair status.
    """
    msg_body = (
        f"Namaskar! A pothole was reported near KM {pothole.get('km_marker', 'N/A')} "
        f"on {pothole.get('highway_id', 'NH-30')} and a government complaint was filed. "
        f"If you recently drove this route, please tell us:\n\n"
        f"Is the road repaired at this location now?\n"
        f"Reply: *1* = Yes, fully fixed\n"
        f"       *2* = No, still damaged\n"
        f"       *3* = Not sure / didn't notice\n\n"
        f"Your response directly triggers government escalation if ignored. "
        f"Thank you. | APIS System | Ref: {pothole.get('uuid', 'N/A')}"
    )
    return await send_whatsapp(user_phone, msg_body)
