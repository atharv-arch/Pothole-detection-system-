# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Citizen Verification ORM Model
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import relationship

from app.database import Base


class CitizenVerification(Base):
    __tablename__ = "citizen_verifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pothole_uuid = Column(Text, ForeignKey("potholes.uuid"))
    phone_hash = Column(Text)
    response = Column(Text, CheckConstraint("response IN ('1','2','3')"))
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    pothole = relationship("Pothole", back_populates="citizen_verifications")

    def __repr__(self) -> str:
        return f"<CitizenVerification {self.id} resp={self.response}>"
