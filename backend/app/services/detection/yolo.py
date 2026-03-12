# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — YOLOv8 Inference Engine
# Section 6: Production model serving, batch inference,
#             severity classification, confidence scoring
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np

from app.config import settings
from app.services.s3 import s3_download_temp, s3_exists

logger = logging.getLogger("apis.yolo")

# Singleton model instance — loaded once at startup
_model = None


def get_model():
    """Load YOLOv8 model (lazy singleton, cached in GPU memory)."""
    global _model
    if _model is not None:
        return _model

    from ultralytics import YOLO

    model_path = settings.YOLO_MODEL_PATH

    # Try local path first, then S3
    if not Path(model_path).exists():
        s3_key = f"models/{Path(model_path).name}"
        if s3_exists(s3_key):
            logger.info("Downloading YOLO model from S3: %s", s3_key)
            model_path = s3_download_temp(s3_key)
        else:
            logger.warning(
                "YOLO model not found at %s or S3. Using pretrained yolov8x-seg.",
                model_path,
            )
            model_path = "yolov8x-seg.pt"

    _model = YOLO(model_path)
    logger.info("YOLOv8 model loaded: %s", model_path)
    return _model


# APIS severity thresholds (area-based classification)
SEVERITY_THRESHOLDS = {
    "critical": 2.0,   # > 2.0 m² → critical
    "high": 1.0,       # 1.0 – 2.0 m² → high
    "medium": 0.3,     # 0.3 – 1.0 m² → medium
    "low": 0.0,        # < 0.3 m² → low
}

# YOLO class name to APIS severity mapping
CLASS_SEVERITY_MAP = {
    "pothole_critical": "critical",
    "pothole_high": "high",
    "pothole_medium": "medium",
    "pothole_low": "low",
    # Fallback for generic model classes
    "pothole": "medium",
    "D40": "medium",       # RDD2022 pothole class
    "D00": "low",          # longitudinal crack
    "D10": "low",          # transverse crack
    "D20": "medium",       # alligator crack
}


def classify_severity(area_sqm: float, yolo_class: str = "") -> str:
    """
    Determine pothole severity from area and/or YOLO class.
    Priority: YOLO class label > area-based classification.
    """
    # Use YOLO class if it maps to a severity
    if yolo_class in CLASS_SEVERITY_MAP:
        return CLASS_SEVERITY_MAP[yolo_class]

    # Fallback: classify by area
    if area_sqm >= SEVERITY_THRESHOLDS["critical"]:
        return "critical"
    elif area_sqm >= SEVERITY_THRESHOLDS["high"]:
        return "high"
    elif area_sqm >= SEVERITY_THRESHOLDS["medium"]:
        return "medium"
    return "low"


def run_inference(
    patch: np.ndarray,
    confidence_threshold: float = None,
    confidence_multiplier: float = 1.0,
) -> list[dict]:
    """
    Run YOLOv8 inference on a single 640×640 patch.

    Returns list of detections:
        [{
            'bbox': [x1, y1, x2, y2],
            'confidence': float,
            'class_name': str,
            'severity': str,
            'mask_polygon': list | None,
            'area_pixels': float,
        }]
    """
    model = get_model()
    threshold = confidence_threshold or settings.YOLO_CONFIDENCE_THRESHOLD

    results = model.predict(
        patch,
        imgsz=640,
        conf=threshold,
        verbose=False,
    )

    detections = []

    for result in results:
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            continue

        for i in range(len(boxes)):
            conf = float(boxes.conf[i]) * confidence_multiplier
            if conf < threshold:
                continue

            class_id = int(boxes.cls[i])
            class_name = result.names.get(class_id, "pothole")

            bbox = boxes.xyxy[i].cpu().numpy().tolist()
            area_pixels = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])

            # Extract segmentation mask polygon if available
            mask_polygon = None
            if result.masks is not None and i < len(result.masks):
                mask = result.masks[i]
                if mask.xy is not None and len(mask.xy) > 0:
                    mask_polygon = mask.xy[0].tolist()

            detection = {
                "bbox": bbox,
                "confidence": round(conf, 3),
                "class_name": class_name,
                "severity": classify_severity(
                    area_pixels / (640 * 640) * 100,  # rough m² estimate
                    class_name,
                ),
                "mask_polygon": mask_polygon,
                "area_pixels": area_pixels,
            }
            detections.append(detection)

    logger.info("YOLO inference: %d detections on patch", len(detections))
    return detections


def run_batch_inference(
    patches: list[np.ndarray],
    source: str = "satellite",
    confidence_multiplier: float = 1.0,
) -> list[list[dict]]:
    """
    Run YOLO inference on a batch of patches.
    Returns list of detection lists (one per patch).
    """
    model = get_model()
    threshold = settings.YOLO_CONFIDENCE_THRESHOLD

    all_detections = []

    # Process in batches of 16
    batch_size = 16
    for batch_start in range(0, len(patches), batch_size):
        batch = patches[batch_start : batch_start + batch_size]

        results = model.predict(
            batch,
            imgsz=640,
            conf=threshold,
            verbose=False,
        )

        for result in results:
            patch_detections = []
            boxes = result.boxes

            if boxes is not None:
                for i in range(len(boxes)):
                    conf = float(boxes.conf[i]) * confidence_multiplier
                    if conf < threshold:
                        continue

                    class_id = int(boxes.cls[i])
                    class_name = result.names.get(class_id, "pothole")
                    bbox = boxes.xyxy[i].cpu().numpy().tolist()
                    area_pixels = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])

                    mask_polygon = None
                    if result.masks is not None and i < len(result.masks):
                        mask = result.masks[i]
                        if mask.xy is not None and len(mask.xy) > 0:
                            mask_polygon = mask.xy[0].tolist()

                    patch_detections.append({
                        "bbox": bbox,
                        "confidence": round(conf, 3),
                        "class_name": class_name,
                        "severity": classify_severity(area_pixels / (640*640)*100, class_name),
                        "mask_polygon": mask_polygon,
                        "area_pixels": area_pixels,
                    })

            all_detections.append(patch_detections)

    total = sum(len(d) for d in all_detections)
    logger.info(
        "Batch YOLO: %d patches → %d total detections (source=%s)",
        len(patches), total, source,
    )
    return all_detections
