# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Social Audit System (Loop Closure Verification)
# Double-layer accountability: AI verification + Citizen audit
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

import logging
from datetime import datetime
from enum import Enum
from typing import Optional

from app.config import settings

logger = logging.getLogger("apis.social_audit")


# ── Verdict Types ─────────────────────────────────────────────
class LoopClosureVerdict(str, Enum):
    """
    Combined AI + Citizen verification verdict.

    The loop closure concept ensures that no repair claim is
    accepted without both automated AI verification (SSIM)
    AND human ground-truth confirmation via Social Audit.
    """
    VERIFIED = "verified"                       # AI + Citizens both confirm repair
    DISPUTED = "disputed"                       # AI says repaired, citizens disagree
    CONFIRMED_UNREPAIRED = "confirmed_unrepaired"  # Both say NOT repaired
    AI_ONLY_VERIFIED = "ai_only_verified"       # AI verified, citizens not yet polled
    PENDING_CITIZEN_AUDIT = "pending_audit"      # Waiting for citizen responses
    WORSENED = "worsened"                        # Citizens report road has worsened


# ── Social Audit Configuration ────────────────────────────────
QUORUM_THRESHOLD = 3        # Minimum citizen responses for valid audit
AGREEMENT_THRESHOLD = 0.6   # 60% agreement needed for consensus
AUDIT_EXPIRY_DAYS = 7       # Audit window: 7 days after poll sent


class SocialAuditRecord:
    """
    Represents a single Social Audit cycle for a pothole repair claim.

    A Social Audit combines:
        1. AI-based SSIM verification (automated)
        2. Citizen ground-truth verification (social audit poll)

    The combined result produces a LoopClosureVerdict.
    """

    def __init__(
        self,
        pothole_uuid: str,
        ai_verdict: str = "PENDING",
        ai_ssim_score: float = 0.0,
    ):
        self.pothole_uuid = pothole_uuid
        self.ai_verdict = ai_verdict
        self.ai_ssim_score = ai_ssim_score
        self.citizen_responses: list[dict] = []
        self.social_audit_score: float = 0.0
        self.loop_closure_verdict: Optional[LoopClosureVerdict] = None
        self.created_at = datetime.now()
        self.audit_id = f"SA-{pothole_uuid[-8:]}-{datetime.now().strftime('%Y%m%d')}"

    def add_citizen_response(self, response_code: str, phone_hash: str) -> None:
        """
        Record a citizen response to the Social Audit poll.

        Response codes:
            1 = Yes, fully repaired
            2 = No, still damaged
            3 = Partially repaired / not sure
            4 = Road condition has worsened
        """
        self.citizen_responses.append({
            "response": response_code,
            "phone_hash": phone_hash,
            "timestamp": datetime.now().isoformat(),
        })
        logger.info(
            "Social audit %s: citizen response=%s (total=%d)",
            self.audit_id, response_code, len(self.citizen_responses),
        )

    def has_quorum(self) -> bool:
        """Check if enough citizen responses have been collected."""
        return len(self.citizen_responses) >= QUORUM_THRESHOLD

    def compute_social_audit_score(self) -> float:
        """
        Compute Social Audit Score (0–100) from citizen responses.

        Scoring:
            Response 1 (Repaired)     → +100 points
            Response 3 (Partial/Unsure) → +30 points
            Response 2 (Not repaired) → +0 points
            Response 4 (Worsened)     → -20 points (penalty)

        Final score = weighted average, normalized to 0–100.
        """
        if not self.citizen_responses:
            return 0.0

        scores = {
            "1": 100,   # Yes, repaired
            "2": 0,     # No, still damaged
            "3": 30,    # Partial / not sure
            "4": -20,   # Worsened
        }

        total = sum(
            scores.get(r["response"], 0)
            for r in self.citizen_responses
        )
        count = len(self.citizen_responses)
        raw_score = total / count

        # Clamp to 0–100
        self.social_audit_score = max(0.0, min(100.0, raw_score))
        return self.social_audit_score

    def compute_loop_closure_verdict(self) -> LoopClosureVerdict:
        """
        Compute the final Loop Closure Verdict by combining:
            1. AI verdict (SSIM-based)
            2. Social Audit score (citizen responses)

        Decision Matrix:
        ┌───────────────────┬────────────────┬─────────────────┐
        │                   │ Citizens: YES  │ Citizens: NO    │
        ├───────────────────┼────────────────┼─────────────────┤
        │ AI: REPAIRED      │ ✅ VERIFIED    │ ⚠️ DISPUTED     │
        │ AI: UNREPAIRED    │ 🔍 Re-inspect  │ ❌ CONFIRMED    │
        └───────────────────┴────────────────┴─────────────────┘
        """
        if not self.has_quorum():
            if self.ai_verdict == "REPAIRED":
                self.loop_closure_verdict = LoopClosureVerdict.AI_ONLY_VERIFIED
            else:
                self.loop_closure_verdict = LoopClosureVerdict.PENDING_CITIZEN_AUDIT
            return self.loop_closure_verdict

        self.compute_social_audit_score()
        ai_says_repaired = self.ai_verdict in ("REPAIRED", "PARTIAL")

        # Check for "worsened" consensus
        worsened_count = sum(
            1 for r in self.citizen_responses if r["response"] == "4"
        )
        if worsened_count / len(self.citizen_responses) >= AGREEMENT_THRESHOLD:
            self.loop_closure_verdict = LoopClosureVerdict.WORSENED
            return self.loop_closure_verdict

        citizens_say_repaired = self.social_audit_score >= 50.0

        if ai_says_repaired and citizens_say_repaired:
            self.loop_closure_verdict = LoopClosureVerdict.VERIFIED
        elif ai_says_repaired and not citizens_say_repaired:
            self.loop_closure_verdict = LoopClosureVerdict.DISPUTED
        elif not ai_says_repaired and not citizens_say_repaired:
            self.loop_closure_verdict = LoopClosureVerdict.CONFIRMED_UNREPAIRED
        else:
            # AI says not repaired but citizens say yes → needs re-inspection
            self.loop_closure_verdict = LoopClosureVerdict.DISPUTED

        logger.info(
            "Loop closure %s: ai=%s, social_score=%.1f, verdict=%s",
            self.audit_id, self.ai_verdict,
            self.social_audit_score, self.loop_closure_verdict.value,
        )
        return self.loop_closure_verdict

    def to_dict(self) -> dict:
        """Serialize audit record for API response."""
        return {
            "audit_id": self.audit_id,
            "pothole_uuid": self.pothole_uuid,
            "ai_verification": {
                "verdict": self.ai_verdict,
                "ssim_score": self.ai_ssim_score,
            },
            "social_audit": {
                "total_responses": len(self.citizen_responses),
                "quorum_met": self.has_quorum(),
                "quorum_threshold": QUORUM_THRESHOLD,
                "social_audit_score": round(self.social_audit_score, 1),
                "responses_summary": self._summarize_responses(),
            },
            "loop_closure_verdict": (
                self.loop_closure_verdict.value
                if self.loop_closure_verdict
                else "pending"
            ),
            "created_at": self.created_at.isoformat(),
        }

    def _summarize_responses(self) -> dict:
        """Summarize citizen responses by category."""
        summary = {
            "repaired": 0,
            "not_repaired": 0,
            "partial_unsure": 0,
            "worsened": 0,
        }
        for r in self.citizen_responses:
            code = r["response"]
            if code == "1":
                summary["repaired"] += 1
            elif code == "2":
                summary["not_repaired"] += 1
            elif code == "3":
                summary["partial_unsure"] += 1
            elif code == "4":
                summary["worsened"] += 1
        return summary


# ── Social Audit Poll Message ─────────────────────────────────
def generate_social_audit_message(pothole: dict) -> str:
    """
    Generate the formal Social Audit poll message.

    This is framed as an official government social audit — not
    just a casual poll. Governments value this framing.
    """
    return (
        f"🏛️ GOVERNMENT SOCIAL AUDIT — Road Repair Verification\n\n"
        f"Under the Social Audit framework for National Highway "
        f"maintenance accountability, we request your ground-truth "
        f"verification:\n\n"
        f"📍 Location: {pothole.get('highway_id', 'NH-30')} "
        f"KM {pothole.get('km_marker', 'N/A')}\n"
        f"📋 APIS Reference: {pothole.get('uuid', 'N/A')}\n"
        f"📅 Repair Claimed: {datetime.now().strftime('%d %B %Y')}\n\n"
        f"If you have recently driven past this location, please "
        f"confirm the road condition:\n\n"
        f"Reply *1* = ✅ Yes, road is fully repaired\n"
        f"Reply *2* = ❌ No, pothole still exists\n"
        f"Reply *3* = ⚠️ Partially fixed / Not sure\n"
        f"Reply *4* = 🔴 Road condition has WORSENED\n\n"
        f"Your response directly determines whether the contractor's "
        f"repair claim is accepted or escalated for re-inspection.\n\n"
        f"— APIS Social Audit System\n"
        f"   CHIPS, Chhattisgarh Infotech Promotion Society\n"
        f"   Ref: {pothole.get('uuid', 'N/A')}"
    )


async def initiate_social_audit(
    pothole: dict,
    ai_verdict: str,
    ai_ssim_score: float,
    citizen_phones: list[str],
) -> SocialAuditRecord:
    """
    Initiate a Social Audit cycle for a pothole repair claim.

    1. Create audit record
    2. Send WhatsApp polls to nearby citizens
    3. Return the audit record (responses arrive via webhook)

    Args:
        pothole: pothole record dict
        ai_verdict: SSIM verification verdict (REPAIRED/PARTIAL/UNREPAIRED)
        ai_ssim_score: SSIM score (0–1)
        citizen_phones: list of phone numbers to poll

    Returns:
        SocialAuditRecord
    """
    audit = SocialAuditRecord(
        pothole_uuid=pothole.get("uuid", "UNKNOWN"),
        ai_verdict=ai_verdict,
        ai_ssim_score=ai_ssim_score,
    )

    # Send WhatsApp Social Audit polls
    message = generate_social_audit_message(pothole)

    try:
        from app.services.twilio_svc import send_social_audit_poll

        for phone in citizen_phones:
            sid = await send_social_audit_poll(pothole, phone)
            if sid:
                logger.info(
                    "Social audit poll sent: %s → %s (SID=%s)",
                    audit.audit_id, phone[-4:], sid,
                )
    except Exception as e:
        logger.error("Failed to send social audit polls: %s", e)

    logger.info(
        "Social audit initiated: %s (ai=%s, ssim=%.4f, polls=%d)",
        audit.audit_id, ai_verdict, ai_ssim_score, len(citizen_phones),
    )

    return audit


def generate_social_audit_certificate(audit: SocialAuditRecord) -> dict:
    """
    Generate a Social Audit Certificate for verified repairs.

    This certificate serves as official documentation that a repair
    has been verified through both AI and citizen confirmation.
    """
    if audit.loop_closure_verdict != LoopClosureVerdict.VERIFIED:
        return {
            "certificate_issued": False,
            "reason": f"Verdict is '{audit.loop_closure_verdict}', not 'verified'",
        }

    return {
        "certificate_issued": True,
        "certificate_number": f"SAC-{audit.audit_id}",
        "title": "SOCIAL AUDIT CERTIFICATE — Repair Verification",
        "pothole_uuid": audit.pothole_uuid,
        "verification_layers": {
            "layer_1_ai": {
                "method": "SSIM (Structural Similarity Index)",
                "score": round(audit.ai_ssim_score, 4),
                "verdict": audit.ai_verdict,
            },
            "layer_2_citizen": {
                "method": "Social Audit — Citizen Ground-Truth Poll",
                "total_responses": len(audit.citizen_responses),
                "social_audit_score": round(audit.social_audit_score, 1),
                "quorum_met": audit.has_quorum(),
            },
        },
        "final_verdict": "REPAIR VERIFIED ✅",
        "issued_at": datetime.now().isoformat(),
        "issued_by": "APIS Social Audit System — CHIPS, Chhattisgarh",
        "note": (
            "This certificate confirms that the pothole repair has been "
            "independently verified through dual-layer accountability: "
            "AI-based image analysis AND citizen social audit. "
            "This document may be used for contractor payment release "
            "and compliance reporting."
        ),
    }
