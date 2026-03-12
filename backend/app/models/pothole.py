# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Pothole ORM Model
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, Numeric, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class Pothole(Base):
    __tablename__ = "potholes"

    uuid = Column(String, primary_key=True)
    gps = Column(Geography("POINT", srid=4326), nullable=False)
    highway_id = Column(Text, nullable=False)
    km_marker = Column(Numeric(6, 1))
    district = Column(Text)
    lane_position = Column(
        Text,
        CheckConstraint("lane_position IN ('centre','left','right','shoulder')"),
    )
    severity = Column(
        Text,
        CheckConstraint("severity IN ('low','medium','high','critical')"),
    )
    risk_score = Column(Numeric(4, 2), CheckConstraint("risk_score BETWEEN 0 AND 10"))
    area_sqm = Column(Numeric(6, 3))
    depth_cm = Column(Numeric(5, 1))
    status = Column(Text, nullable=False, default="detected")
    source_primary = Column(
        Text,
        CheckConstraint("source_primary IN ('satellite','cctv','mobile','sar')"),
    )
    confidence = Column(Numeric(4, 3), CheckConstraint("confidence BETWEEN 0 AND 1"))
    first_detected = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_scanned = Column(DateTime(timezone=True))
    weather_at_detection = Column(JSONB)
    repair_verified = Column(Boolean, default=False)
    ssim_score = Column(Numeric(4, 3))
    image_before = Column(Text)
    image_after = Column(Text)
    yolo_mask_polygon = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    complaints = relationship("Complaint", back_populates="pothole", cascade="all, delete-orphan")
    scan_history = relationship("ScanHistory", back_populates="pothole", order_by="ScanHistory.scanned_at.desc()")
    citizen_verifications = relationship("CitizenVerification", back_populates="pothole")

    @property
    def lat(self) -> float | None:
        if self.gps is not None:
            from geoalchemy2.shape import to_shape
            point = to_shape(self.gps)
            return point.y
        return None

    @property
    def lon(self) -> float | None:
        if self.gps is not None:
            from geoalchemy2.shape import to_shape
            point = to_shape(self.gps)
            return point.x
        return None

    def __repr__(self) -> str:
        return f"<Pothole {self.uuid} [{self.severity}] risk={self.risk_score}>"
