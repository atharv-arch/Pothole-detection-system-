# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Mobile Reports API Router
# Section 4: Mobile report ingestion, GPS validation, YOLO queue
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import MobileReport, MobileReportResponse

router = APIRouter(prefix="/api/reports", tags=["Reports"])


@router.post("/mobile", response_model=MobileReportResponse)
async def ingest_mobile_report(
    report: MobileReport,
    db: AsyncSession = Depends(get_db),
):
    """
    Ingest a mobile accelerometer/camera report.

    Pipeline:
        1. Validate GPS is on a known highway (PostGIS buffer)
        2. Duplicate check (same device, same location, 24h)
        3. Insert report
        4. If VIBRATION_REPORT: check pocket cluster trigger
        5. If VISUAL_EVIDENCE: queue YOLO inference on video
    """
    # Step 1 — Validate GPS on highway
    highway_check = await db.execute(
        text("""
            SELECT highway_id, km_marker
            FROM highway_segments
            WHERE ST_DWithin(
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                road_buffer::geography,
                75
            )
            ORDER BY ST_Distance(
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                road_buffer::geography
            )
            LIMIT 1
        """),
        {"lat": report.lat, "lon": report.lon},
    )
    on_highway = highway_check.fetchone()

    if not on_highway:
        return MobileReportResponse(
            status="ignored", reason="not_on_highway", points=0
        )

    hwy = on_highway._mapping

    # Step 2 — Duplicate check
    existing = await db.execute(
        text("""
            SELECT id FROM source_reports
            WHERE ST_DWithin(
                gps::geography,
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                30
            )
            AND device_id = :did
            AND timestamp > NOW() - INTERVAL '24 hours'
        """),
        {"lon": report.lon, "lat": report.lat, "did": report.device_id},
    )
    if existing.fetchone():
        return MobileReportResponse(status="duplicate", points=0)

    # Step 3 — Insert report
    await db.execute(
        text("""
            INSERT INTO source_reports
            (source, gps, jolt_magnitude, speed_kmh, device_id,
             video_s3_url, report_type, highway_id, km_marker, timestamp)
            VALUES ('MOBILE',
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
                    :jolt, :speed, :did, :video, :rtype, :hid, :km, :ts)
        """),
        {
            "lon": report.lon,
            "lat": report.lat,
            "jolt": report.jolt_magnitude,
            "speed": report.speed_kmh,
            "did": report.device_id,
            "video": report.video_s3_url,
            "rtype": report.type,
            "hid": hwy["highway_id"],
            "km": hwy["km_marker"],
            "ts": report.timestamp,
        },
    )

    # Step 4 — Pocket cluster trigger
    if report.type == "VIBRATION_REPORT":
        await _check_cluster_trigger(report.lat, report.lon, db)

    # Step 5 — YOLO queue for visual evidence
    if report.video_s3_url:
        try:
            from app.tasks.filing_tasks import run_yolo_on_video

            run_yolo_on_video.delay(
                report.video_s3_url, report.lat, report.lon, report.device_id
            )
        except Exception:
            pass  # Celery not available — skip async YOLO

    points = 10 if report.type == "VISUAL_EVIDENCE" else 3
    return MobileReportResponse(status="accepted", points=points)


async def _check_cluster_trigger(lat: float, lon: float, db: AsyncSession):
    """
    Check if enough pocket vibration reports cluster around this point
    to justify triggering a satellite/CCTV verification.

    Cluster criteria: >= 3 distinct devices within 50m in the last 7 days.
    """
    result = await db.execute(
        text("""
            SELECT COUNT(DISTINCT device_id) as device_count
            FROM source_reports
            WHERE report_type = 'VIBRATION_REPORT'
              AND processed = FALSE
              AND ST_DWithin(
                  gps::geography,
                  ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                  50
              )
              AND timestamp > NOW() - INTERVAL '7 days'
        """),
        {"lat": lat, "lon": lon},
    )
    row = result.fetchone()
    if row and row._mapping["device_count"] >= 3:
        # Flag cluster — will be picked up by mobile_cluster_check DAG
        await db.execute(
            text("""
                UPDATE source_reports SET processed = TRUE
                WHERE report_type = 'VIBRATION_REPORT'
                  AND ST_DWithin(
                      gps::geography,
                      ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                      50
                  )
                  AND timestamp > NOW() - INTERVAL '7 days'
            """),
            {"lat": lat, "lon": lon},
        )
