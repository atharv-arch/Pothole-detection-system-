# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Potholes API Router
# Section 14: CRUD, GeoJSON, timeline, images
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import (
    PotholeResponse, PotholeGeoJSON, TimelineEvent,
)

router = APIRouter(prefix="/api/potholes", tags=["Potholes"])


@router.get("", response_model=list[PotholeResponse])
async def list_potholes(
    highway: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = Query(None),
    km_start: Optional[float] = None,
    km_end: Optional[float] = None,
    bbox: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List potholes with filtering, sorted by risk_score DESC."""
    query = "SELECT *, ST_Y(gps::geometry) as lat, ST_X(gps::geometry) as lon FROM potholes WHERE 1=1"
    params = {}

    if highway:
        query += " AND highway_id = :highway"
        params["highway"] = highway
    if severity:
        sevs = severity.split(",")
        query += " AND severity = ANY(:sevs)"
        params["sevs"] = sevs
    if status:
        query += " AND status = :status"
        params["status"] = status
    if km_start is not None:
        query += " AND km_marker >= :km_start"
        params["km_start"] = km_start
    if km_end is not None:
        query += " AND km_marker <= :km_end"
        params["km_end"] = km_end
    if bbox:
        parts = [float(x) for x in bbox.split(",")]
        if len(parts) == 4:
            query += """
                AND ST_Within(gps::geometry,
                    ST_MakeEnvelope(:west, :south, :east, :north, 4326))
            """
            params.update(
                {"south": parts[0], "west": parts[1],
                 "north": parts[2], "east": parts[3]}
            )

    query += " ORDER BY risk_score DESC NULLS LAST LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    return [
        PotholeResponse(
            **{k: v for k, v in row._mapping.items()
               if k not in ("lat", "lon")},
            lat=row._mapping.get("lat"),
            lon=row._mapping.get("lon"),
        )
        for row in rows
    ]


@router.get("/geojson")
async def get_potholes_geojson(
    highway: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """GeoJSON FeatureCollection of all active potholes (cached in Redis)."""
    query = """
        SELECT uuid, ST_AsGeoJSON(gps)::json as geometry,
               highway_id, km_marker, severity, risk_score,
               status, source_primary, confidence, first_detected
        FROM potholes
        WHERE status NOT IN ('verified_repaired', 'removed')
    """
    params = {}
    if highway:
        query += " AND highway_id = :highway"
        params["highway"] = highway

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    features = []
    for row in rows:
        m = row._mapping
        features.append({
            "type": "Feature",
            "geometry": m["geometry"],
            "properties": {
                "uuid": m["uuid"],
                "highway_id": m["highway_id"],
                "km_marker": float(m["km_marker"]) if m["km_marker"] else None,
                "severity": m["severity"],
                "risk_score": float(m["risk_score"]) if m["risk_score"] else None,
                "status": m["status"],
                "source": m["source_primary"],
                "confidence": float(m["confidence"]) if m["confidence"] else None,
            },
        })

    return {"type": "FeatureCollection", "features": features}


@router.get("/{uuid}")
async def get_pothole(uuid: str, db: AsyncSession = Depends(get_db)):
    """Get full pothole record — the 'pothole passport'."""
    result = await db.execute(
        text("""
            SELECT *, ST_Y(gps::geometry) as lat, ST_X(gps::geometry) as lon
            FROM potholes WHERE uuid = :uuid
        """),
        {"uuid": uuid},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Pothole not found")

    pothole = dict(row._mapping)

    # Fetch complaints
    complaints = await db.execute(
        text("SELECT * FROM complaints WHERE pothole_uuid = :uuid ORDER BY filed_at DESC"),
        {"uuid": uuid},
    )
    pothole["complaints"] = [dict(c._mapping) for c in complaints.fetchall()]

    # Fetch scan history
    scans = await db.execute(
        text("SELECT * FROM scan_history WHERE pothole_uuid = :uuid ORDER BY scanned_at DESC"),
        {"uuid": uuid},
    )
    pothole["scan_history"] = [dict(s._mapping) for s in scans.fetchall()]

    # Fetch escalations
    escalations = await db.execute(
        text("""
            SELECT el.* FROM escalation_log el
            JOIN complaints c ON el.complaint_id = c.complaint_id
            WHERE c.pothole_uuid = :uuid
            ORDER BY el.escalated_at
        """),
        {"uuid": uuid},
    )
    pothole["escalations"] = [dict(e._mapping) for e in escalations.fetchall()]

    return pothole


@router.get("/{uuid}/timeline", response_model=list[TimelineEvent])
async def get_pothole_timeline(uuid: str, db: AsyncSession = Depends(get_db)):
    """Chronological event timeline for a pothole."""
    events = []

    # Detection event
    result = await db.execute(
        text("SELECT * FROM potholes WHERE uuid = :uuid"), {"uuid": uuid}
    )
    pothole = result.fetchone()
    if not pothole:
        raise HTTPException(status_code=404, detail="Pothole not found")

    p = pothole._mapping
    events.append(TimelineEvent(
        event="DETECTED", timestamp=p["first_detected"],
        detail=f"Detected via {p['source_primary']} (confidence: {p['confidence']})"
    ))

    if p["risk_score"]:
        events.append(TimelineEvent(
            event="RISK_SCORED", timestamp=p["first_detected"],
            detail=f"Risk score: {p['risk_score']}/10 ({p['severity']})"
        ))

    # Complaints
    complaints = await db.execute(
        text("SELECT * FROM complaints WHERE pothole_uuid = :uuid ORDER BY filed_at"),
        {"uuid": uuid},
    )
    for c in complaints.fetchall():
        cm = c._mapping
        if cm["filed_at"]:
            events.append(TimelineEvent(
                event="COMPLAINT_FILED", timestamp=cm["filed_at"],
                detail=f"Filed on {cm['portal']} (Ref: {cm['reference_number'] or 'pending'})"
            ))

    # Scans
    scans = await db.execute(
        text("SELECT * FROM scan_history WHERE pothole_uuid = :uuid ORDER BY scanned_at"),
        {"uuid": uuid},
    )
    for s in scans.fetchall():
        sm = s._mapping
        events.append(TimelineEvent(
            event="RESCAN", timestamp=sm["scanned_at"],
            ssim=float(sm["ssim_vs_prev"]) if sm["ssim_vs_prev"] else None,
            verdict=sm["verdict"],
        ))

    # Escalations
    escalations = await db.execute(
        text("""
            SELECT el.* FROM escalation_log el
            JOIN complaints c ON el.complaint_id = c.complaint_id
            WHERE c.pothole_uuid = :uuid ORDER BY el.escalated_at
        """),
        {"uuid": uuid},
    )
    for e in escalations.fetchall():
        em = e._mapping
        events.append(TimelineEvent(
            event=f"ESCALATED_T{em['tier_to']}",
            timestamp=em["escalated_at"],
            detail=em["reason"],
        ))

    # Citizen verifications
    verifs = await db.execute(
        text("""
            SELECT response, COUNT(*) as cnt
            FROM citizen_verifications
            WHERE pothole_uuid = :uuid
            GROUP BY response
        """),
        {"uuid": uuid},
    )
    for v in verifs.fetchall():
        vm = v._mapping
        label = {"1": "YES", "2": "NO", "3": "UNSURE"}.get(vm["response"], vm["response"])
        events.append(TimelineEvent(
            event=f"CITIZEN_{label}", count=int(vm["cnt"])
        ))

    # Sort by timestamp
    events.sort(key=lambda e: e.timestamp or datetime.min)
    return events


@router.get("/{uuid}/images")
async def get_pothole_images(uuid: str, db: AsyncSession = Depends(get_db)):
    """Get signed S3 URLs for before/after/diff images."""
    from app.services.s3 import s3_get_signed_url

    result = await db.execute(
        text("SELECT image_before, image_after FROM potholes WHERE uuid = :uuid"),
        {"uuid": uuid},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Pothole not found")

    m = row._mapping
    images = {}
    if m["image_before"]:
        images["before"] = s3_get_signed_url(m["image_before"])
    if m["image_after"]:
        images["after"] = s3_get_signed_url(m["image_after"])

    # Latest diff map
    diff = await db.execute(
        text("""
            SELECT diff_map_path FROM scan_history
            WHERE pothole_uuid = :uuid AND diff_map_path IS NOT NULL
            ORDER BY scanned_at DESC LIMIT 1
        """),
        {"uuid": uuid},
    )
    diff_row = diff.fetchone()
    if diff_row and diff_row._mapping["diff_map_path"]:
        images["diff"] = s3_get_signed_url(diff_row._mapping["diff_map_path"])

    return images


# Need to import datetime for timeline
from datetime import datetime


@router.get("/{uuid}/work-order")
async def get_work_order(uuid: str, db: AsyncSession = Depends(get_db)):
    """
    Generate a Standardized Repair Work Order for a pothole.

    Returns actionable data: material BoQ, cost estimate,
    repair method per IRC/CPWD standards, and contractor instructions.
    """
    from app.services.work_order import generate_work_order, generate_work_order_pdf

    result = await db.execute(
        text("""
            SELECT *, ST_Y(gps::geometry) as lat, ST_X(gps::geometry) as lon
            FROM potholes WHERE uuid = :uuid
        """),
        {"uuid": uuid},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Pothole not found")

    pothole = dict(row._mapping)

    # Fetch highway segment data
    road_result = await db.execute(
        text("""
            SELECT * FROM highway_segments
            WHERE highway_id = :hid
              AND km_start <= :km AND km_end >= :km
            LIMIT 1
        """),
        {"hid": pothole.get("highway_id"), "km": pothole.get("km_marker", 0)},
    )
    road_row = road_result.fetchone()
    road = dict(road_row._mapping) if road_row else {
        "highway_id": pothole.get("highway_id", "NH-30"),
        "district": pothole.get("district", "Raipur"),
    }

    work_order = generate_work_order(pothole, road)

    # Generate PDF (async, non-blocking)
    pdf_path = generate_work_order_pdf(work_order)
    if pdf_path:
        work_order["pdf_url"] = pdf_path

    return work_order
