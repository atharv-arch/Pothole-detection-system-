# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Celery Async Task Workers
# Celery app configuration + async tasks for YOLO, filing
# ═══════════════════════════════════════════════════════════════

from celery import Celery

from app.config import settings

celery_app = Celery(
    "apis_tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
