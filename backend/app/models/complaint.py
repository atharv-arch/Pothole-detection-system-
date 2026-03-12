# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Complaint ORM Model
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func, CheckConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class Complaint(Base):
    __tablename__ = "complaints"

    complaint_id = Column(String, primary_key=True, server_default=func.gen_random_uuid().cast(String))
    pothole_uuid = Column(String, ForeignKey("potholes.uuid", ondelete="CASCADE"))
    portal = Column(Text, nullable=False)
    filed_at = Column(DateTime(timezone=True))
    reference_number = Column(Text)
    tier = Column(Integer, default=1, info={"check": CheckConstraint("tier BETWEEN 1 AND 3")})
    sla_deadline = Column(DateTime(timezone=True))
    escalated_at = Column(DateTime(timezone=True))
    resolved_at = Column(DateTime(timezone=True))
    letter_text = Column(Text)
    letter_pdf_s3 = Column(Text)
    confirmation_s3 = Column(Text)
    status = Column(Text, default="pending")
    filing_method = Column(Text, default="selenium")

    # Relationships
    pothole = relationship("Pothole", back_populates="complaints")
    escalations = relationship("EscalationLog", back_populates="complaint")

    def __repr__(self) -> str:
        return f"<Complaint {self.complaint_id} tier={self.tier} status={self.status}>"
