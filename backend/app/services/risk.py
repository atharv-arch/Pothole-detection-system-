# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Risk Score Computation Engine
# Section 7: Multi-factor risk formula with accident history,
#             speed limits, traffic, weather, geometry
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

import logging

logger = logging.getLogger("apis.risk")

# Severity weights
SEVERITY_WEIGHTS = {
    "critical": 4.0,
    "high": 3.0,
    "medium": 2.0,
    "low": 1.0,
}


def compute_risk_score(
    pothole: dict,
    road: dict,
    weather: dict,
    accidents: int,
) -> float:
    """
    Compute multi-factor risk score (0–10 scale).

    Production formula combining:
        - Pothole severity
        - Accident history within 1 km (iRAD/MoRTH)
        - Speed limit (OSM)
        - Traffic density (NHAI AADT)
        - Road curvature
        - Night accident ratio
        - Current weather (rain)
        - Pothole depth
        - Lane position

    Args:
        pothole: {severity, depth_cm, lane_position, ...}
        road: {speed_limit_kmh, aadt, is_curve, night_accident_ratio, ...}
        weather: {is_raining, ...}
        accidents: int — count of pothole-related accidents in 1 km / 1 year

    Returns:
        Risk score 0.0 – 10.0
    """
    # Base components (additive)
    sev = SEVERITY_WEIGHTS.get(pothole.get("severity", "medium"), 2.0)
    acc = min(accidents / 3.0, 4.0)
    spd = min(road.get("speed_limit_kmh", 80) / 60.0, 2.0)
    trfc = min(road.get("aadt", 5000) / 5000.0, 2.0)
    depth = min(pothole.get("depth_cm", 5.0) / 10.0, 1.5)

    # Multiplicative factors
    curve = 1.5 if road.get("is_curve", False) else 1.0
    night = 1.3 if road.get("night_accident_ratio", 0) > 0.4 else 1.0
    rain = 1.2 if weather.get("is_raining", False) else 1.0
    lane_c = 1.4 if pothole.get("lane_position") == "centre" else 1.0

    # Compute raw score
    raw = (sev + acc + spd + trfc + depth) * curve * night * rain * lane_c

    # Normalize to 0–10 scale
    score = min(raw / 16.0 * 10.0, 10.0)
    score = round(score, 2)

    logger.info(
        "Risk score: sev=%.1f acc=%.1f spd=%.1f trfc=%.1f depth=%.1f "
        "× curve=%.1f night=%.1f rain=%.1f lane=%.1f → raw=%.2f → score=%.2f",
        sev, acc, spd, trfc, depth, curve, night, rain, lane_c, raw, score,
    )
    return score


def compute_stretch_risk(
    highway_id: str,
    km_start: float,
    km_end: float,
    potholes: list[dict],
) -> float:
    """
    Compute aggregate risk score for a highway stretch.
    Averages individual pothole risk scores, weighted by severity.
    """
    if not potholes:
        return 0.0

    total_weight = 0.0
    weighted_sum = 0.0

    for p in potholes:
        weight = SEVERITY_WEIGHTS.get(p.get("severity", "low"), 1.0)
        weighted_sum += p.get("risk_score", 0) * weight
        total_weight += weight

    stretch_risk = weighted_sum / total_weight if total_weight > 0 else 0.0
    return round(min(stretch_risk, 10.0), 2)


def determine_alert_level(risk_score: float) -> str:
    """
    Map risk score to human-readable alert level.
    """
    if risk_score >= 8.0:
        return "CRITICAL"
    elif risk_score >= 6.0:
        return "HIGH"
    elif risk_score >= 4.0:
        return "MODERATE"
    elif risk_score >= 2.0:
        return "LOW"
    return "MINIMAL"
