# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Patch Slicing & Pixel-to-GPS Conversion
# Section 2: 640×640 patches with overlap, pyproj geo-conversion
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
from pyproj import Transformer

logger = logging.getLogger("apis.patches")

# UTM Zone 44N → WGS84 (covers Chhattisgarh)
_transformer = Transformer.from_crs("EPSG:32644", "EPSG:4326", always_xy=True)


def slice_to_patches(
    image_array: np.ndarray,
    patch_size: int = 640,
    overlap: float = 0.10,
) -> tuple[list[np.ndarray], list[tuple[int, int]]]:
    """
    Slice a large image into overlapping patches for YOLO inference.

    Args:
        image_array: (H, W, C) numpy array
        patch_size: side length of each square patch
        overlap: fractional overlap between adjacent patches

    Returns:
        patches: list of (patch_size, patch_size, C) arrays
        coords: list of (x, y) top-left pixel coordinates
    """
    step = int(patch_size * (1 - overlap))
    H, W = image_array.shape[:2]
    patches = []
    coords = []

    for y in range(0, H - patch_size + 1, step):
        for x in range(0, W - patch_size + 1, step):
            patch = image_array[y : y + patch_size, x : x + patch_size]
            patches.append(patch)
            coords.append((x, y))

    logger.info(
        "Sliced %dx%d image → %d patches (size=%d, overlap=%.0f%%)",
        W, H, len(patches), patch_size, overlap * 100,
    )
    return patches, coords


def pixel_to_gps(
    pixel_x: int, pixel_y: int, geotransform: tuple
) -> tuple[float, float]:
    """
    Convert pixel coordinates to GPS (lat, lon) using geotransform.

    Geotransform format (from rasterio):
        (x_origin, pixel_width, x_rotation, y_origin, y_rotation, pixel_height)

    Or as Affine transform:
        geotransform = (a, b, c, d, e, f)
        where c=x_origin, a=pixel_width, f=y_origin, e=pixel_height

    Returns:
        (latitude, longitude) in WGS84
    """
    # Unpack geotransform — handle both 6-tuple and Affine
    if len(geotransform) == 6:
        a, b, c, d, e, f = geotransform
    else:
        # Fallback for dict-like
        c = geotransform[2]  # x origin
        a = geotransform[0]  # pixel width
        f = geotransform[5]  # y origin
        e = geotransform[4]  # pixel height

    map_x = c + pixel_x * a
    map_y = f + pixel_y * e

    lon, lat = _transformer.transform(map_x, map_y)
    return lat, lon


def detection_pixel_to_gps(
    det_bbox: list[float],
    patch_x: int,
    patch_y: int,
    geotransform: tuple,
) -> tuple[float, float]:
    """
    Convert a YOLO detection bbox centre to GPS coordinates.

    Args:
        det_bbox: [x1, y1, x2, y2] in patch pixel coords
        patch_x: top-left X of this patch in the full image
        patch_y: top-left Y of this patch in the full image
        geotransform: rasterio geotransform of the full image

    Returns:
        (lat, lon) of the detection centre
    """
    centre_x = (det_bbox[0] + det_bbox[2]) / 2 + patch_x
    centre_y = (det_bbox[1] + det_bbox[3]) / 2 + patch_y
    return pixel_to_gps(int(centre_x), int(centre_y), geotransform)


def estimate_area_sqm(
    det_bbox: list[float],
    pixel_resolution_m: float = 10.0,
) -> float:
    """
    Estimate pothole area in m² from YOLO bbox and pixel resolution.

    Args:
        det_bbox: [x1, y1, x2, y2] in pixels
        pixel_resolution_m: ground sampling distance (10m for Sentinel-2)

    Returns:
        Estimated area in square metres
    """
    width_px = det_bbox[2] - det_bbox[0]
    height_px = det_bbox[3] - det_bbox[1]

    # Scale factor: how much of the original image each YOLO pixel represents
    # For satellite at 10m/pixel, a 640px YOLO patch covers ~6400m
    width_m = width_px * pixel_resolution_m
    height_m = height_px * pixel_resolution_m
    area_sqm = width_m * height_m

    return round(area_sqm, 3)
