# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — CCTV Node ORM Model
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

from geoalchemy2 import Geography
from sqlalchemy import Boolean, Column, DateTime, Numeric, Text
from sqlalchemy.orm import relationship

from app.database import Base


class CCTVNode(Base):
    __tablename__ = "cctv_nodes"

    camera_id = Column(Text, primary_key=True)
    gps = Column(Geography("POINT", srid=4326))
    highway_id = Column(Text)
    km_marker = Column(Numeric(6, 1))
    rtsp_url = Column(Text)
    atms_zone = Column(Text)
    is_online = Column(Boolean, default=True)
    last_checked = Column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<CCTVNode {self.camera_id} online={self.is_online}>"
