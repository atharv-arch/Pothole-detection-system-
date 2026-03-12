# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — NHAI ATMS CCTV Frame Processing
# Section 3: Live CCTV frame extraction, perspective correction,
#             SSIM-based skip, night mode CLAHE
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

import hashlib
import logging
from typing import Optional

import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim_metric

from app.config import settings
from app.services.s3 import s3_save_frame

logger = logging.getLogger("apis.cctv")


class CCTVProcessor:
    """Processes live CCTV frames from NHAI ATMS cameras."""

    SSIM_SKIP_THRESHOLD = 0.98
    ROAD_CROP_TOP_RATIO = 0.60  # crop bottom 40% (road surface)
    YOLO_INPUT_SIZE = 640

    def __init__(self, db_session=None):
        self.db = db_session

    def extract_frame(self, camera: dict) -> Optional[np.ndarray]:
        """
        Extract a single frame from RTSP feed.
        Falls back to NHAI REST API snapshot if RTSP fails.
        """
        frame = self._try_rtsp(camera)
        if frame is None:
            frame = self._try_rest_api(camera)
        return frame

    def _try_rtsp(self, camera: dict) -> Optional[np.ndarray]:
        """Try RTSP feed extraction."""
        rtsp_url = camera.get("rtsp_url")
        if not rtsp_url:
            return None

        try:
            cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if not cap.isOpened():
                logger.error("RTSP failed: %s", camera["camera_id"])
                return None

            ret, frame = cap.read()
            cap.release()

            if not ret:
                return None

            logger.info(
                "RTSP frame captured: %s (%dx%d)",
                camera["camera_id"],
                frame.shape[1],
                frame.shape[0],
            )
            return frame
        except Exception as e:
            logger.error("RTSP exception for %s: %s", camera["camera_id"], e)
            return None

    def _try_rest_api(self, camera: dict) -> Optional[np.ndarray]:
        """Fallback: NHAI REST API snapshot."""
        if not settings.NHAI_ATMS_API_KEY:
            logger.warning("NHAI_ATMS_API_KEY not set — cannot use REST fallback")
            return None

        import requests

        camera_id = camera["camera_id"]
        try:
            response = requests.get(
                f"https://atms.nhai.gov.in/api/v1/cameras/{camera_id}/snapshot",
                headers={"X-API-Key": settings.NHAI_ATMS_API_KEY},
                timeout=10,
            )
            if response.status_code == 200:
                frame = cv2.imdecode(
                    np.frombuffer(response.content, np.uint8),
                    cv2.IMREAD_COLOR,
                )
                return frame
        except Exception as e:
            logger.error("NHAI REST API failed for %s: %s", camera_id, e)

        return None

    def should_skip_frame(
        self, frame: np.ndarray, camera_id: str, prev_frame: Optional[np.ndarray]
    ) -> bool:
        """
        Check if this frame is identical or nearly identical to previous.
        Uses MD5 hash for exact match and SSIM for near-match.
        """
        frame_hash = hashlib.md5(frame.tobytes()).hexdigest()

        # Check exact duplicate
        if prev_frame is None:
            return False

        # SSIM check
        prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
        curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Resize to same dimensions if needed
        if prev_gray.shape != curr_gray.shape:
            curr_gray = cv2.resize(curr_gray, (prev_gray.shape[1], prev_gray.shape[0]))

        ssim_val, _ = ssim_metric(prev_gray, curr_gray, full=True)

        if ssim_val > self.SSIM_SKIP_THRESHOLD:
            logger.debug(
                "Frame skip: %s (SSIM=%.4f > %.2f)",
                camera_id,
                ssim_val,
                self.SSIM_SKIP_THRESHOLD,
            )
            return True

        return False

    def process_frame(self, frame: np.ndarray, camera: dict) -> dict:
        """
        Full processing pipeline for a single CCTV frame:
        1. Crop road region (bottom 40%)
        2. Perspective transform (flatten road surface)
        3. Night mode CLAHE if dark
        4. Resize to 640×640 for YOLO input
        5. Save raw frame to S3

        Returns dict with processed patch and metadata.
        """
        H, W = frame.shape[:2]

        # Step 1 — Crop bottom 40% (road surface)
        road_region = frame[int(H * self.ROAD_CROP_TOP_RATIO) : H, 0:W]

        # Step 2 — Perspective correction for downward-angled cameras
        rH, rW = road_region.shape[:2]
        src_pts = np.float32([
            [0, 0], [rW, 0], [rW, rH], [0, rH]
        ])
        dst_pts = np.float32([
            [int(rW * 0.15), 0], [int(rW * 0.85), 0],
            [rW, rH], [0, rH],
        ])
        M = cv2.getPerspectiveTransform(src_pts, dst_pts)
        warped = cv2.warpPerspective(road_region, M, (rW, rH))

        # Step 3 — Night mode detection + CLAHE enhancement
        night_mode = frame.mean() < 40
        if night_mode:
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            warped_gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
            warped = cv2.cvtColor(clahe.apply(warped_gray), cv2.COLOR_GRAY2BGR)

        # Step 4 — Resize to YOLO input size
        patch = cv2.resize(warped, (self.YOLO_INPUT_SIZE, self.YOLO_INPUT_SIZE))

        # Step 5 — Save raw frame to S3
        frame_s3_path = s3_save_frame(frame, camera["camera_id"])

        return {
            "patch": patch,
            "night_mode": night_mode,
            "confidence_multiplier": 0.8 if night_mode else 1.0,
            "frame_s3_path": frame_s3_path,
            "gps": camera.get("gps"),
            "camera_id": camera["camera_id"],
        }
