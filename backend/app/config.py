# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Configuration (Pydantic Settings)
# All environment variables from Section 1 of the production spec
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

import logging
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("apis.config")


class Settings(BaseSettings):
    """
    Central configuration loaded from environment variables.
    Optional keys log warnings on missing — they do NOT crash the app.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # ── Database (required) ───────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/apis"
    DATABASE_SYNC_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/apis"

    # ── Redis ─────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── S3 / Object Storage ───────────────────────────────────
    S3_BUCKET_NAME: str = "apis-imagery"
    AWS_REGION: str = "ap-south-1"
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None

    # ── ESA Copernicus (Sentinel) ─────────────────────────────
    COPERNICUS_USER: Optional[str] = None
    COPERNICUS_PASS: Optional[str] = None

    # ── Google Gemini AI ──────────────────────────────────────
    GEMINI_API_KEY: Optional[str] = None

    # ── PG Portal ─────────────────────────────────────────────
    PGPORTAL_USER: Optional[str] = None
    PGPORTAL_PASS: Optional[str] = None

    # ── Twilio (WhatsApp + SMS) ───────────────────────────────
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_WHATSAPP_FROM: Optional[str] = None
    TWILIO_SMS_FROM: Optional[str] = None

    # ── India Meteorological Department ───────────────────────
    IMD_API_KEY: Optional[str] = None

    # ── NHAI ATMS CCTV ────────────────────────────────────────
    NHAI_ATMS_API_KEY: Optional[str] = None

    # ── Firebase ──────────────────────────────────────────────
    FIREBASE_SERVICE_ACCOUNT: Optional[str] = None

    # ── Mapbox ────────────────────────────────────────────────
    MAPBOX_ACCESS_TOKEN: Optional[str] = None

    # ── MLflow ────────────────────────────────────────────────
    MLFLOW_TRACKING_URI: Optional[str] = None

    # ── System Identity ──────────────────────────────────────
    SYSTEM_EMAIL: Optional[str] = None
    SYSTEM_EMAIL_PASS: Optional[str] = None
    SYSTEM_PHONE: Optional[str] = None

    # ── CAPTCHA solver ────────────────────────────────────────
    TWO_CAPTCHA_API_KEY: Optional[str] = None

    # ── YOLO model path ───────────────────────────────────────
    YOLO_MODEL_PATH: str = "models/yolov8x_nh30_v1.pt"
    YOLO_CONFIDENCE_THRESHOLD: float = 0.45

    # ── Region defaults (NH-30) ───────────────────────────────
    NH30_BBOX_SW_LAT: float = 21.2514
    NH30_BBOX_SW_LON: float = 81.6293
    NH30_BBOX_NE_LAT: float = 22.0847
    NH30_BBOX_NE_LON: float = 82.1847

    # ── Application ───────────────────────────────────────────
    APP_NAME: str = "Autonomous Pothole Intelligence System (APIS)"
    APP_VERSION: str = "5.0"
    DEBUG: bool = False
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    def warn_missing(self) -> None:
        """Log warnings for missing optional credentials."""
        optional_keys = [
            ("COPERNICUS_USER", "Sentinel satellite downloads"),
            ("GEMINI_API_KEY", "AI complaint letter generation"),
            ("PGPORTAL_USER", "PG Portal automated filing"),
            ("TWILIO_ACCOUNT_SID", "WhatsApp/SMS notifications"),
            ("NHAI_ATMS_API_KEY", "NHAI CCTV access"),
            ("MAPBOX_ACCESS_TOKEN", "Dashboard map rendering"),
        ]
        for key, feature in optional_keys:
            if getattr(self, key, None) is None:
                logger.warning(
                    "ENV %s not set — %s will be unavailable", key, feature
                )


settings = Settings()
