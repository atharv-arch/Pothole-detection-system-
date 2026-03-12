# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Pydantic Schemas (Request/Response Models)
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Pothole Schemas ───────────────────────────────────────────

class PotholeBase(BaseModel):
    uuid: str
    highway_id: str
    km_marker: Optional[float] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    district: Optional[str] = None
    lane_position: Optional[str] = None
    severity: Optional[str] = None
    risk_score: Optional[float] = None
    area_sqm: Optional[float] = None
    depth_cm: Optional[float] = None
    status: str = "detected"
    source_primary: Optional[str] = None
    confidence: Optional[float] = None


class PotholeResponse(PotholeBase):
    first_detected: Optional[datetime] = None
    last_scanned: Optional[datetime] = None
    repair_verified: bool = False
    ssim_score: Optional[float] = None
    image_before: Optional[str] = None
    image_after: Optional[str] = None
    weather_at_detection: Optional[dict] = None

    class Config:
        from_attributes = True


class PotholeDetailResponse(PotholeResponse):
    complaints: list[ComplaintResponse] = []
    scan_history: list[ScanHistoryResponse] = []
    timeline: list[TimelineEvent] = []


class PotholeGeoJSON(BaseModel):
    type: str = "FeatureCollection"
    features: list[dict] = []


# ── Timeline Event ────────────────────────────────────────────

class TimelineEvent(BaseModel):
    event: str
    timestamp: Optional[datetime] = None
    detail: Optional[str] = None
    ssim: Optional[float] = None
    verdict: Optional[str] = None
    count: Optional[int] = None


# ── Complaint Schemas ─────────────────────────────────────────

class ComplaintResponse(BaseModel):
    complaint_id: str
    pothole_uuid: Optional[str] = None
    portal: str
    filed_at: Optional[datetime] = None
    reference_number: Optional[str] = None
    tier: int = 1
    sla_deadline: Optional[datetime] = None
    status: Optional[str] = None
    letter_pdf_s3: Optional[str] = None
    confirmation_s3: Optional[str] = None

    class Config:
        from_attributes = True


# ── Escalation ────────────────────────────────────────────────

class EscalationResponse(BaseModel):
    id: int
    complaint_id: Optional[str] = None
    pothole_uuid: Optional[str] = None
    tier_from: Optional[int] = None
    tier_to: Optional[int] = None
    escalated_at: Optional[datetime] = None
    reason: Optional[str] = None
    days_since_original: Optional[int] = None

    class Config:
        from_attributes = True


# ── Scan History ──────────────────────────────────────────────

class ScanHistoryResponse(BaseModel):
    scan_id: int
    scanned_at: Optional[datetime] = None
    source: Optional[str] = None
    confidence: Optional[float] = None
    ssim_vs_prev: Optional[float] = None
    verdict: Optional[str] = None

    class Config:
        from_attributes = True


# ── Mobile Report ─────────────────────────────────────────────

class MobileReport(BaseModel):
    type: str = Field(..., description="VISUAL_EVIDENCE or VIBRATION_REPORT")
    lat: float
    lon: float
    speed_kmh: Optional[float] = None
    jolt_magnitude: Optional[float] = None
    video_s3_url: Optional[str] = None
    timestamp: Optional[str] = None
    device_id: Optional[str] = None


class MobileReportResponse(BaseModel):
    status: str
    reason: Optional[str] = None
    points: int = 0


# ── Highway Stretch ───────────────────────────────────────────

class StretchResponse(BaseModel):
    highway_id: str
    km_start: Optional[float] = None
    km_end: Optional[float] = None
    stretch_risk: float = 0.0
    alert_level: str = "MINIMAL"
    pothole_count: int = 0
    critical_count: int = 0
    active_complaints: int = 0


# ── Analytics ─────────────────────────────────────────────────

class AnalyticsSummary(BaseModel):
    total_active: int = 0
    total_repaired: int = 0
    total_complaints_filed: int = 0
    total_sla_breached: int = 0
    avg_risk_score: float = 0.0
    detections_last_7d: int = 0
    repairs_verified: int = 0
    highways_monitored: int = 0
    severity_distribution: dict = {}
    source_distribution: dict = {}
    monthly_trend: list[dict] = []


# ── Predictive ────────────────────────────────────────────────

class PredictiveResponse(BaseModel):
    uuid: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    highway_id: Optional[str] = None
    km_marker: Optional[float] = None
    probability: Optional[float] = None
    confidence: Optional[float] = None
    estimated_days: Optional[int] = None
    status: str = "pred_unconfirmed"


# ── Citizen Verification ─────────────────────────────────────

class CitizenVerifyRequest(BaseModel):
    Body: str
    From: str


# Forward references
PotholeDetailResponse.model_rebuild()
