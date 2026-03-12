# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Highway Stretches & Analytics API Routers
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import StretchResponse, AnalyticsSummary
from app.services.risk import determine_alert_level

stretches_router = APIRouter(prefix="/api/stretches", tags=["Stretches"])
analytics_router = APIRouter(prefix="/api/analytics", tags=["Analytics"])
predict_router = APIRouter(prefix="/api/predict", tags=["Predictive"])


# ── Highway Stretches ─────────────────────────────────────────

@stretches_router.get("", response_model=list[StretchResponse])
async def list_stretches(db: AsyncSession = Depends(get_db)):
    """All highways with stretch risk score, alert level, pothole counts."""
    result = await db.execute(
        text("""
            SELECT
                p.highway_id,
                MIN(p.km_marker) as km_start,
                MAX(p.km_marker) as km_end,
                AVG(p.risk_score) as stretch_risk,
                COUNT(*) as pothole_count,
                COUNT(*) FILTER (WHERE p.severity = 'critical') as critical_count,
                COUNT(DISTINCT c.complaint_id) FILTER (
                    WHERE c.status NOT IN ('resolved', 'verified_repaired')
                ) as active_complaints
            FROM potholes p
            LEFT JOIN complaints c ON p.uuid = c.pothole_uuid
            WHERE p.status NOT IN ('verified_repaired', 'removed')
            GROUP BY p.highway_id
            ORDER BY stretch_risk DESC NULLS LAST
        """)
    )
    rows = result.fetchall()
    stretches = []
    for row in rows:
        m = row._mapping
        risk = float(m["stretch_risk"]) if m["stretch_risk"] else 0.0
        stretches.append(StretchResponse(
            highway_id=m["highway_id"],
            km_start=float(m["km_start"]) if m["km_start"] else None,
            km_end=float(m["km_end"]) if m["km_end"] else None,
            stretch_risk=round(risk, 2),
            alert_level=determine_alert_level(risk),
            pothole_count=m["pothole_count"],
            critical_count=m["critical_count"],
            active_complaints=m["active_complaints"],
        ))
    return stretches


@stretches_router.get("/{highway_id}")
async def get_stretch_detail(
    highway_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Per-km breakdown of risk for a highway (heatmap data)."""
    result = await db.execute(
        text("""
            SELECT
                FLOOR(km_marker) as km,
                COUNT(*) as pothole_count,
                AVG(risk_score) as avg_risk,
                MAX(risk_score) as max_risk,
                array_agg(uuid) as uuids,
                array_agg(severity) as severities
            FROM potholes
            WHERE highway_id = :hid
              AND status NOT IN ('verified_repaired', 'removed')
              AND km_marker IS NOT NULL
            GROUP BY FLOOR(km_marker)
            ORDER BY FLOOR(km_marker)
        """),
        {"hid": highway_id},
    )
    return [dict(row._mapping) for row in result.fetchall()]


# ── Analytics ─────────────────────────────────────────────────

@analytics_router.get("/summary", response_model=AnalyticsSummary)
async def get_analytics_summary(db: AsyncSession = Depends(get_db)):
    """Dashboard KPI summary statistics."""
    stats = {}

    # Core counts
    result = await db.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE status NOT IN ('verified_repaired','removed')) as total_active,
                COUNT(*) FILTER (WHERE status = 'verified_repaired') as total_repaired,
                COUNT(*) FILTER (WHERE repair_verified = TRUE) as repairs_verified,
                AVG(risk_score) FILTER (WHERE status NOT IN ('verified_repaired','removed')) as avg_risk,
                COUNT(*) FILTER (WHERE first_detected > NOW() - INTERVAL '7 days') as detections_last_7d,
                COUNT(DISTINCT highway_id) as highways_monitored
            FROM potholes
        """)
    )
    row = result.fetchone()._mapping
    stats.update({
        "total_active": row["total_active"] or 0,
        "total_repaired": row["total_repaired"] or 0,
        "repairs_verified": row["repairs_verified"] or 0,
        "avg_risk_score": round(float(row["avg_risk"] or 0), 2),
        "detections_last_7d": row["detections_last_7d"] or 0,
        "highways_monitored": row["highways_monitored"] or 0,
    })

    # Complaint counts
    result = await db.execute(
        text("""
            SELECT
                COUNT(*) as total_complaints,
                COUNT(*) FILTER (WHERE status IN ('escalated_l2','escalated_l3','sla_breach_public'))
                    as total_sla_breached
            FROM complaints
        """)
    )
    cm = result.fetchone()._mapping
    stats["total_complaints_filed"] = cm["total_complaints"] or 0
    stats["total_sla_breached"] = cm["total_sla_breached"] or 0

    # Severity distribution
    result = await db.execute(
        text("""
            SELECT severity, COUNT(*) as count
            FROM potholes
            WHERE status NOT IN ('verified_repaired','removed')
            GROUP BY severity
        """)
    )
    stats["severity_distribution"] = {
        row._mapping["severity"]: row._mapping["count"]
        for row in result.fetchall() if row._mapping["severity"]
    }

    # Source distribution
    result = await db.execute(
        text("""
            SELECT source_primary, COUNT(*) as count
            FROM potholes WHERE source_primary IS NOT NULL
            GROUP BY source_primary
        """)
    )
    stats["source_distribution"] = {
        row._mapping["source_primary"]: row._mapping["count"]
        for row in result.fetchall()
    }

    # Monthly trend (last 6 months)
    result = await db.execute(
        text("""
            SELECT
                DATE_TRUNC('month', first_detected) as month,
                COUNT(*) as detected,
                COUNT(*) FILTER (WHERE status = 'verified_repaired') as repaired
            FROM potholes
            WHERE first_detected > NOW() - INTERVAL '6 months'
            GROUP BY DATE_TRUNC('month', first_detected)
            ORDER BY month
        """)
    )
    stats["monthly_trend"] = [
        {
            "month": row._mapping["month"].isoformat() if row._mapping["month"] else None,
            "detected": row._mapping["detected"],
            "repaired": row._mapping["repaired"],
        }
        for row in result.fetchall()
    ]

    return AnalyticsSummary(**stats)


# ── Predictive ────────────────────────────────────────────────

@predict_router.get("")
async def list_predictions(db: AsyncSession = Depends(get_db)):
    """All SAR-predicted potholes (PRED-xxx)."""
    result = await db.execute(
        text("""
            SELECT uuid, ST_Y(gps::geometry) as lat, ST_X(gps::geometry) as lon,
                   highway_id, km_marker, confidence, severity, status,
                   first_detected
            FROM potholes
            WHERE uuid LIKE 'PRED-%'
            ORDER BY confidence DESC
        """)
    )
    return [dict(row._mapping) for row in result.fetchall()]
