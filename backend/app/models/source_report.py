# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Source Report ORM Model (Mobile / CCTV / Satellite)
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

from geoalchemy2 import Geography
from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, Text, func
from sqlalchemy.orm import relationship

from app.database import Base


class SourceReport(Base):
    __tablename__ = "source_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(Text)
    gps = Column(Geography("POINT", srid=4326))
    highway_id = Column(Text)
    km_marker = Column(Numeric(6, 1))
    jolt_magnitude = Column(Numeric(5, 3))
    speed_kmh = Column(Numeric(5, 1))
    device_id = Column(Text)
    video_s3_url = Column(Text)
    report_type = Column(Text)
    processed = Column(Boolean, default=False)
    pothole_uuid = Column(Text)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<SourceReport {self.id} src={self.source} type={self.report_type}>"
