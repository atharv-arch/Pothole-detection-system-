# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Spatial Deduplication
# PostGIS-based pothole dedup (ST_DWithin 20m merge)
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

import logging
from datetime import datetime
from secrets import token_hex

logger = logging.getLogger("apis.dedup")


def generate_pothole_uuid() -> str:
    """Generate a PTH-xxxxxxxx UUID for new potholes."""
    return f"PTH-{datetime.now().strftime('%Y%m%d')}-{token_hex(3).upper()}"


async def deduplicate_detections(
    detections: list[dict],
    db_session,
    merge_radius_m: float = 20.0,
) -> list[dict]:
    """
    Spatially deduplicate detections against existing potholes in DB.

    For each detection:
        1. Query existing potholes within merge_radius_m
        2. If match found: update existing (increase confidence, update scan time)
        3. If no match: assign new PTH-UUID and insert

    Args:
        detections: list of detection dicts with 'lat', 'lon' keys
        db_session: async SQLAlchemy session
        merge_radius_m: merge distance in metres

    Returns:
        List of new/updated pothole dicts ready for insertion
    """
    from sqlalchemy import text

    new_potholes = []
    updated_count = 0

    for det in detections:
        lat = det.get("lat")
        lon = det.get("lon")

        if lat is None or lon is None:
            logger.warning("Detection missing GPS, skipping: %s", det)
            continue

        # Check for existing pothole within merge radius
        result = await db_session.execute(
            text("""
                SELECT uuid, confidence, status
                FROM potholes
                WHERE ST_DWithin(
                    gps::geography,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                    :radius
                )
                ORDER BY ST_Distance(
                    gps::geography,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
                )
                LIMIT 1
            """),
            {"lat": lat, "lon": lon, "radius": merge_radius_m},
        )
        existing = result.fetchone()

        if existing:
            # Update existing pothole — merge confidence
            existing_uuid = existing[0]
            existing_conf = float(existing[1] or 0)
            new_conf = min(
                (existing_conf + det.get("confidence", 0.5)) / 1.5,
                0.999,
            )

            await db_session.execute(
                text("""
                    UPDATE potholes
                    SET confidence = :conf,
                        last_scanned = NOW(),
                        updated_at = NOW()
                    WHERE uuid = :uuid
                """),
                {"conf": round(new_conf, 3), "uuid": existing_uuid},
            )
            updated_count += 1
            det["uuid"] = existing_uuid
            det["is_new"] = False
        else:
            # New pothole
            det["uuid"] = generate_pothole_uuid()
            det["is_new"] = True
            new_potholes.append(det)

    logger.info(
        "Dedup: %d detections → %d new, %d merged with existing",
        len(detections), len(new_potholes), updated_count,
    )
    return detections
