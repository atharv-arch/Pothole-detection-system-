# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Weather Data Service (Open-Meteo + IMD)
# Section 5: Live weather at detection point, 7-day rainfall,
#             monsoon detection, WMO code mapping
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger("apis.weather")

# WMO weather code → human readable label
WMO_CODE_MAP = {
    0: "Clear",
    1: "Mainly Clear",
    2: "Partly Cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing Rime Fog",
    51: "Light Drizzle",
    53: "Moderate Drizzle",
    55: "Dense Drizzle",
    56: "Light Freezing Drizzle",
    57: "Dense Freezing Drizzle",
    61: "Slight Rain",
    63: "Moderate Rain",
    65: "Heavy Rain",
    66: "Light Freezing Rain",
    67: "Heavy Freezing Rain",
    71: "Slight Snow",
    73: "Moderate Snow",
    75: "Heavy Snow",
    77: "Snow Grains",
    80: "Slight Rain Showers",
    81: "Moderate Rain Showers",
    82: "Violent Rain Showers",
    85: "Slight Snow Showers",
    86: "Heavy Snow Showers",
    95: "Thunderstorm",
    96: "Thunderstorm with Slight Hail",
    99: "Thunderstorm with Heavy Hail",
}

MONSOON_RAINFALL_THRESHOLD_7D_MM = 50.0


def map_wmo_code(code: int) -> str:
    """Convert WMO weather code to human-readable label."""
    return WMO_CODE_MAP.get(code, f"Code {code}")


async def get_weather_at_point(lat: float, lon: float) -> dict:
    """
    Fetch live weather and 7-day rainfall history for a GPS point.

    Uses Open-Meteo API (free, no key required, 1km resolution).
    Fallback to default values if API is unreachable.

    Returns:
        {
            'is_raining': bool,
            'rainfall_mm': float,       # current precipitation
            'rainfall_7d_mm': float,    # cumulative 7-day total
            'temp_c': float,
            'condition': str,           # human readable
            'windspeed_kmh': float,
            'monsoon_active': bool,     # True if 7d rainfall > 50mm
        }
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,precipitation,rain,weathercode,windspeed_10m",
        "hourly": "precipitation",
        "past_days": 7,
        "forecast_days": 1,
        "timezone": "Asia/Kolkata",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        current = data["current"]
        # Sum hourly precipitation for past 7 days (168 hours)
        hourly_precip = data.get("hourly", {}).get("precipitation", [])
        rain_7d = sum(hourly_precip[:168]) if hourly_precip else 0.0

        weather = {
            "is_raining": current.get("rain", 0) > 0,
            "rainfall_mm": current.get("precipitation", 0),
            "rainfall_7d_mm": round(rain_7d, 1),
            "temp_c": current.get("temperature_2m", 0),
            "condition": map_wmo_code(current.get("weathercode", 0)),
            "windspeed_kmh": current.get("windspeed_10m", 0),
            "monsoon_active": rain_7d > MONSOON_RAINFALL_THRESHOLD_7D_MM,
        }

        logger.info(
            "Weather at (%.4f, %.4f): %s, rain=%.1fmm, 7d=%.1fmm",
            lat, lon, weather["condition"],
            weather["rainfall_mm"], weather["rainfall_7d_mm"],
        )
        return weather

    except Exception as e:
        logger.error("Weather API failed: %s — using defaults", e)
        return {
            "is_raining": False,
            "rainfall_mm": 0.0,
            "rainfall_7d_mm": 0.0,
            "temp_c": 30.0,
            "condition": "Unknown",
            "windspeed_kmh": 0.0,
            "monsoon_active": False,
        }


def get_weather_sync(lat: float, lon: float) -> dict:
    """Synchronous wrapper for Celery/Airflow tasks."""
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(
                    asyncio.run, get_weather_at_point(lat, lon)
                ).result()
    except RuntimeError:
        pass

    return asyncio.run(get_weather_at_point(lat, lon))
