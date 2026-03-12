# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Celery Async Tasks (YOLO + Filing)
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from app.tasks.celery_app import celery_app

logger = logging.getLogger("apis.tasks")


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def run_yolo_on_video(self, video_s3_url: str, lat: float, lon: float, device_id: str):
    """Run YOLOv8 inference on a mobile-captured video clip."""
    try:
        import cv2
        from app.services.s3 import s3_download_temp
        from app.services.detection.yolo import run_inference
        from app.database import SyncSessionLocal

        local_path = s3_download_temp(video_s3_url)
        cap = cv2.VideoCapture(local_path)
        detections = []

        frame_count = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            frame_count += 1
            if frame_count % 15 == 0:  # sample every 0.5s at 30fps
                patch = cv2.resize(frame, (640, 640))
                dets = run_inference(patch, confidence_multiplier=0.9)
                detections.extend(dets)

        cap.release()

        if detections:
            logger.info(
                "Video YOLO: %d detections from %s", len(detections), video_s3_url
            )
            # Insert findings into DB via sync session
            session = SyncSessionLocal()
            try:
                from sqlalchemy import text
                for det in detections:
                    session.execute(
                        text("""
                            INSERT INTO source_reports
                            (source, gps, device_id, video_s3_url,
                             report_type, processed)
                            VALUES ('MOBILE',
                                    ST_SetSRID(ST_MakePoint(:lon,:lat),4326),
                                    :did, :video, 'VISUAL_YOLO', TRUE)
                        """),
                        {"lon": lon, "lat": lat, "did": device_id,
                         "video": video_s3_url},
                    )
                session.commit()
            finally:
                session.close()

        return {"detections": len(detections)}

    except Exception as exc:
        logger.error("YOLO video task failed: %s", exc)
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60,
                 autoretry_for=(Exception,))
def file_complaint_task(self, complaint_id: str):
    """File a complaint on PG Portal with retry logic."""
    from app.database import SyncSessionLocal
    from app.services.pgportal import file_on_pgportal, fallback_email_complaint
    from sqlalchemy import text

    session = SyncSessionLocal()
    try:
        row = session.execute(
            text("SELECT * FROM complaints WHERE complaint_id = :cid"),
            {"cid": complaint_id},
        ).fetchone()

        if not row:
            logger.error("Complaint %s not found", complaint_id)
            return

        complaint = dict(row._mapping)

        try:
            ref = file_on_pgportal(complaint)
            session.execute(
                text("""
                    UPDATE complaints
                    SET reference_number = :ref, status = 'filed',
                        filed_at = :now
                    WHERE complaint_id = :cid
                """),
                {"ref": ref, "now": datetime.utcnow(), "cid": complaint_id},
            )
            session.commit()
            logger.info("Complaint %s filed: ref=%s", complaint_id, ref)

        except Exception as exc:
            if self.request.retries >= self.max_retries:
                logger.warning("Max retries reached — falling back to email")
                fallback_email_complaint(complaint)
                session.execute(
                    text("""
                        UPDATE complaints
                        SET status = 'filed_via_email', filed_at = :now
                        WHERE complaint_id = :cid
                    """),
                    {"now": datetime.utcnow(), "cid": complaint_id},
                )
                session.commit()
            else:
                raise self.retry(
                    exc=exc, countdown=60 * (2 ** self.request.retries)
                )
    finally:
        session.close()
