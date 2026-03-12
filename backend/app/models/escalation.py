# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Escalation Log ORM Model
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Serial, String, Text, func
from sqlalchemy.orm import relationship

from app.database import Base


class EscalationLog(Base):
    __tablename__ = "escalation_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    complaint_id = Column(String, ForeignKey("complaints.complaint_id"))
    pothole_uuid = Column(Text)
    tier_from = Column(Integer)
    tier_to = Column(Integer)
    escalated_at = Column(DateTime(timezone=True), server_default=func.now())
    reason = Column(Text)
    new_ref_number = Column(Text)
    rti_reference = Column(Text)
    gemini_letter = Column(Text)
    sms_sid = Column(Text)
    days_since_original = Column(Integer)

    # Relationships
    complaint = relationship("Complaint", back_populates="escalations")

    def __repr__(self) -> str:
        return f"<Escalation {self.id} T{self.tier_from}→T{self.tier_to}>"
