# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — FastAPI Main Application Entry Point
# Section 14: All routers, middleware, startup events
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

# Configure structured logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("apis")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("═" * 60)
    logger.info("  APIS v%s — Starting up...", settings.APP_VERSION)
    logger.info("═" * 60)

    # Warn about missing optional credentials
    settings.warn_missing()

    yield  # App runs here

    logger.info("APIS shutting down...")


app = FastAPI(
    title="APIS — Autonomous Pothole Intelligence System",
    description=(
        "Production AI system for autonomous pothole detection, "
        "complaint filing, and three-tier escalation on National Highways. "
        "Deployed by CHIPS, Chhattisgarh."
    ),
    version=settings.APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

# ── CORS Middleware ───────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS + [
        "https://apis.chips.cg.gov.in",
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Register Routers ─────────────────────────────────────────
from app.api.potholes import router as potholes_router
from app.api.complaints import router as complaints_router
from app.api.reports import router as reports_router
from app.api.stretches import stretches_router, analytics_router, predict_router
from app.api.citizen import router as citizen_router

app.include_router(potholes_router)
app.include_router(complaints_router)
app.include_router(reports_router)
app.include_router(stretches_router)
app.include_router(analytics_router)
app.include_router(predict_router)
app.include_router(citizen_router)


# ── Health Check ──────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health_check():
    return {
        "status": "healthy",
        "system": "APIS",
        "version": settings.APP_VERSION,
    }


@app.get("/", tags=["System"])
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/api/docs",
        "description": (
            "Autonomous Pothole Intelligence System — "
            "NH-30 Raipur–Bilaspur Corridor Monitoring"
        ),
    }
