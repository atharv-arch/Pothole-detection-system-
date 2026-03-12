# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Scan History ORM Model
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, Text, func
from sqlalchemy.orm import relationship

from app.database import Base


class ScanHistory(Base):
    __tablename__ = "scan_history"

    scan_id = Column(Integer, primary_key=True, autoincrement=True)
    pothole_uuid = Column(Text, ForeignKey("potholes.uuid"))
    scanned_at = Column(DateTime(timezone=True), server_default=func.now())
    source = Column(Text)
    confidence = Column(Numeric(4, 3))
    image_path = Column(Text)
    ssim_vs_prev = Column(Numeric(4, 3))
    diff_map_path = Column(Text)
    verdict = Column(Text)
    yolo_detected = Column(Boolean)

    # Relationships
    pothole = relationship("Pothole", back_populates="scan_history")

    def __repr__(self) -> str:
        return f"<Scan {self.scan_id} {self.verdict} ssim={self.ssim_vs_prev}>"
