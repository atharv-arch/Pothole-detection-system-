# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — MiDaS v3 Depth Estimation
# Section 6: Relative depth → absolute depth (cm) calibration
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger("apis.depth")

_midas_model = None
_midas_transform = None

# Empirical scale factor: 1 MiDaS unit ≈ 0.8 cm on NH-30
DEPTH_SCALE_FACTOR = 0.8


def _load_midas():
    """Lazy-load MiDaS v3 small model."""
    global _midas_model, _midas_transform

    if _midas_model is not None:
        return _midas_model, _midas_transform

    import torch

    _midas_model = torch.hub.load(
        "intel-isl/MiDaS", "MiDaS_small", pretrained=True
    )
    _midas_model.eval()

    transforms = torch.hub.load("intel-isl/MiDaS", "transforms")
    _midas_transform = transforms.small_transform

    logger.info("MiDaS v3 small model loaded successfully")
    return _midas_model, _midas_transform


def estimate_depth_cm(pothole_crop: np.ndarray) -> float:
    """
    Estimate pothole depth in centimetres using MiDaS v3.

    Method:
        1. Run MiDaS relative depth estimation
        2. Compute baseline = median depth of outer 20% (flat road)
        3. Compute pothole_min = minimum depth in crop centre
        4. relative_depth = baseline - pothole_min
        5. absolute_depth = relative_depth * DEPTH_SCALE_FACTOR

    Args:
        pothole_crop: BGR numpy array of the pothole region

    Returns:
        Estimated depth in cm (positive = depression)
    """
    import torch

    model, transform = _load_midas()

    # MiDaS expects RGB
    if len(pothole_crop.shape) == 3 and pothole_crop.shape[2] == 3:
        import cv2
        rgb_crop = cv2.cvtColor(pothole_crop, cv2.COLOR_BGR2RGB)
    else:
        rgb_crop = pothole_crop

    input_batch = transform(rgb_crop).unsqueeze(0)

    with torch.no_grad():
        depth_map = model(input_batch)

    depth_map = depth_map.squeeze().cpu().numpy()

    # Baseline: median depth of outer 20% of patch (flat road surface)
    flat_threshold = np.percentile(depth_map, 20)
    baseline = np.median(depth_map[depth_map < flat_threshold])

    # Pothole minimum depth
    pothole_min = depth_map.min()

    # Relative depression
    relative_d = baseline - pothole_min

    # Scale to absolute cm
    depth_cm = round(float(relative_d) * DEPTH_SCALE_FACTOR, 1)

    logger.info(
        "Depth estimation: baseline=%.2f, min=%.2f, relative=%.2f, depth=%.1f cm",
        baseline, pothole_min, relative_d, depth_cm,
    )

    return max(depth_cm, 0.0)  # ensure non-negative
