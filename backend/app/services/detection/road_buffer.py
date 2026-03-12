# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Road Buffer Extraction from OpenStreetMap
# Section 2: Overpass API for NH centrelines, Shapely 50m buffer
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

import json
import logging
from pathlib import Path

from shapely.geometry import LineString, mapping
from shapely.ops import unary_union

from app.config import settings

logger = logging.getLogger("apis.road_buffer")

# Cache directory for road buffer GeoJSON
CACHE_DIR = Path("/tmp/apis_road_buffers")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Buffer distance in decimal degrees: ~50m at ~22°N latitude
BUFFER_DEGREES = 0.00045


def fetch_highway_centreline(
    highway_ref: str = "NH-30",
    bbox: tuple[float, float, float, float] | None = None,
) -> LineString:
    """
    Fetch highway centreline from OpenStreetMap via Overpass API.

    Args:
        highway_ref: highway reference tag (e.g. "NH-30", "NH-53")
        bbox: (south, west, north, east) bounding box

    Returns:
        Shapely LineString of the highway centreline
    """
    import overpy

    if bbox is None:
        bbox = (
            settings.NH30_BBOX_SW_LAT,
            settings.NH30_BBOX_SW_LON,
            settings.NH30_BBOX_NE_LAT,
            settings.NH30_BBOX_NE_LON,
        )

    api = overpy.Overpass()
    query = f"""
        way["ref"="{highway_ref}"]["highway"~"trunk|primary|motorway"]
        ({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
        out geom;
    """

    logger.info("Querying Overpass for %s centreline...", highway_ref)
    result = api.query(query)

    if not result.ways:
        raise ValueError(
            f"No highway ways found for ref={highway_ref} in bbox={bbox}"
        )

    # Collect all node coordinates from all ways
    coords = []
    for way in result.ways:
        for node in way.nodes:
            coords.append((float(node.lon), float(node.lat)))

    if len(coords) < 2:
        raise ValueError(f"Insufficient coordinates for {highway_ref}: {len(coords)}")

    road_line = LineString(coords)
    logger.info(
        "%s centreline: %d coordinates, length ~%.1f km",
        highway_ref,
        len(coords),
        road_line.length * 111,  # rough degree → km
    )
    return road_line


def create_road_buffer(
    highway_ref: str = "NH-30",
    buffer_m: float = 50.0,
    bbox: tuple | None = None,
) -> dict:
    """
    Create a ~50m road buffer GeoJSON polygon.

    Uses cached version if available to avoid repeated Overpass calls.

    Returns:
        GeoJSON geometry dict (Polygon/MultiPolygon)
    """
    cache_file = CACHE_DIR / f"{highway_ref.replace('-', '_')}_buffer.geojson"

    # Check cache
    if cache_file.exists():
        logger.info("Using cached road buffer: %s", cache_file)
        with open(cache_file) as f:
            return json.load(f)

    # Fetch centreline
    centreline = fetch_highway_centreline(highway_ref, bbox)

    # Buffer: ~50m in decimal degrees
    buffer_deg = buffer_m / 111_000  # rough conversion
    road_buffer = centreline.buffer(buffer_deg)

    # Convert to GeoJSON
    geojson = mapping(road_buffer)

    # Cache it
    with open(cache_file, "w") as f:
        json.dump(geojson, f)

    logger.info(
        "Created %s road buffer: ~%.0fm, cached at %s",
        highway_ref, buffer_m, cache_file,
    )
    return geojson


def get_speed_limits(
    highway_ref: str = "NH-30",
    bbox: tuple | None = None,
) -> list[dict]:
    """
    Fetch speed limit data from OSM maxspeed tags.

    Returns list of segments with speed limits:
        [{'km_start': float, 'km_end': float, 'speed_limit_kmh': int}]
    """
    import overpy

    if bbox is None:
        bbox = (
            settings.NH30_BBOX_SW_LAT,
            settings.NH30_BBOX_SW_LON,
            settings.NH30_BBOX_NE_LAT,
            settings.NH30_BBOX_NE_LON,
        )

    api = overpy.Overpass()
    query = f"""
        way["ref"="{highway_ref}"]["maxspeed"]
        ({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
        out tags geom;
    """

    try:
        result = api.query(query)
    except Exception as e:
        logger.warning("Overpass speed limit query failed: %s", e)
        return [{"km_start": 0, "km_end": 999, "speed_limit_kmh": 80}]

    segments = []
    for way in result.ways:
        speed_str = way.tags.get("maxspeed", "80")
        speed_kmh = int(speed_str.replace(" km/h", "").replace(" mph", ""))
        segments.append({
            "way_id": way.id,
            "speed_limit_kmh": speed_kmh,
            "nodes": len(way.nodes),
        })

    if not segments:
        segments = [{"km_start": 0, "km_end": 999, "speed_limit_kmh": 80}]

    logger.info("Found %d speed-limit segments for %s", len(segments), highway_ref)
    return segments
