# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Highway Segment & Accident History ORM Models
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

from geoalchemy2 import Geography
from sqlalchemy import Boolean, Column, Date, Integer, Numeric, Text
from sqlalchemy.orm import relationship

from app.database import Base


class HighwaySegment(Base):
    __tablename__ = "highway_segments"

    segment_id = Column(Integer, primary_key=True, autoincrement=True)
    highway_id = Column(Text)
    km_start = Column(Numeric(6, 1))
    km_end = Column(Numeric(6, 1))
    road_buffer = Column(Geography("POLYGON", srid=4326))
    speed_limit_kmh = Column(Integer)
    aadt = Column(Integer)
    is_curve = Column(Boolean, default=False)
    road_age_years = Column(Numeric(4, 1))
    district = Column(Text)
    night_accident_ratio = Column(Numeric(4, 3))

    def __repr__(self) -> str:
        return f"<HighwaySegment {self.highway_id} KM {self.km_start}–{self.km_end}>"


class AccidentHistory(Base):
    __tablename__ = "accident_history"

    accident_id = Column(Integer, primary_key=True, autoincrement=True)
    highway_id = Column(Text)
    km_marker = Column(Numeric(6, 1))
    accident_date = Column(Date)
    severity = Column(Text)
    vehicle_type = Column(Text)
    cause = Column(Text)
    lat = Column(Numeric(9, 6))
    lon = Column(Numeric(9, 6))

    def __repr__(self) -> str:
        return f"<Accident {self.accident_id} {self.highway_id} KM{self.km_marker}>"
