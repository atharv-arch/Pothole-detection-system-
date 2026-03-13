# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — SSIM Repair Verification Pipeline
# Section 11: ORB alignment + region-focused SSIM comparison
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

import logging
from datetime import date, datetime

import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim

from app.services.s3 import s3_download_temp, s3_save_image

logger = logging.getLogger("apis.verification")

# SSIM thresholds for repair verdict
REPAIRED_THRESHOLD = 0.88
PARTIAL_THRESHOLD = 0.70


def verify_repair_production(
    pothole_uuid: str,
    new_image_path: str,
    before_image_s3: str,
    pothole_mask: list | None = None,
) -> dict:
    """
    Verify pothole repair by comparing before/after images using SSIM.

    Pipeline:
        1. Load before (S3) and after (new scan) images
        2. Align images using ORB feature matching + homography
        3. Compute full-image SSIM
        4. If YOLO mask available: compute region-focused SSIM
        5. Generate diff visualization
        6. Return verdict: REPAIRED / PARTIAL / UNREPAIRED

    Args:
        pothole_uuid: pothole UUID
        new_image_path: local path to new scan image
        before_image_s3: S3 key of the original detection image
        pothole_mask: optional YOLO mask polygon for region focus

    Returns:
        {
            'ssim': float,
            'verdict': str,          # REPAIRED / PARTIAL / UNREPAIRED
            'diff_s3': str,          # S3 path of diff visualization
            'region_ssim': float,    # pothole-region SSIM if mask available
        }
    """
    # Load images
    before = cv2.imread(s3_download_temp(before_image_s3))
    after = cv2.imread(new_image_path)

    if before is None or after is None:
        raise ValueError(f"Image not found for {pothole_uuid}")

    # ── Step 1: ORB Feature Matching + Homography Alignment ───
    orb = cv2.ORB_create(1000)
    kp1, d1 = orb.detectAndCompute(
        cv2.cvtColor(before, cv2.COLOR_BGR2GRAY), None
    )
    kp2, d2 = orb.detectAndCompute(
        cv2.cvtColor(after, cv2.COLOR_BGR2GRAY), None
    )

    if d1 is not None and d2 is not None:
        matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = sorted(matcher.match(d1, d2), key=lambda m: m.distance)[:50]

        if len(matches) >= 10:
            pts1 = np.float32([kp1[m.queryIdx].pt for m in matches])
            pts2 = np.float32([kp2[m.trainIdx].pt for m in matches])
            H, _ = cv2.findHomography(pts2, pts1, cv2.RANSAC, 5.0)
            if H is not None:
                after = cv2.warpPerspective(
                    after, H, (before.shape[1], before.shape[0])
                )

    # Resize to same dimensions
    after = cv2.resize(after, (before.shape[1], before.shape[0]))

    # ── Step 2: Full SSIM ─────────────────────────────────────
    b_gray = cv2.cvtColor(before, cv2.COLOR_BGR2GRAY).astype(np.float32)
    a_gray = cv2.cvtColor(after, cv2.COLOR_BGR2GRAY).astype(np.float32)

    ssim_score, diff_map = ssim(b_gray, a_gray, full=True, data_range=255)

    # ── Step 3: Region-Focused SSIM (YOLO mask) ──────────────
    region_ssim = ssim_score  # default to full SSIM

    if pothole_mask is not None and len(pothole_mask) > 0:
        try:
            # Create binary mask from polygon
            mask_pts = np.array(pothole_mask, dtype=np.int32)
            binary_mask = np.zeros(b_gray.shape[:2], dtype=np.uint8)
            cv2.fillPoly(binary_mask, [mask_pts], 255)

            region_before = cv2.bitwise_and(
                b_gray.astype(np.uint8), b_gray.astype(np.uint8),
                mask=binary_mask,
            )
            region_after = cv2.bitwise_and(
                a_gray.astype(np.uint8), a_gray.astype(np.uint8),
                mask=binary_mask,
            )

            region_ssim, _ = ssim(
                region_before.astype(np.float32),
                region_after.astype(np.float32),
                full=True,
                data_range=255,
            )
        except Exception as e:
            logger.warning("Region SSIM failed: %s — using full SSIM", e)

    # ── Step 4: Diff Visualization ────────────────────────────
    diff_vis = (diff_map * 255).astype(np.uint8)
    diff_s3 = s3_save_image(
        diff_vis, f"diffs/{pothole_uuid}_diff_{date.today()}.jpg"
    )

    # ── Step 5: Verdict ───────────────────────────────────────
    if region_ssim > REPAIRED_THRESHOLD:
        verdict = "REPAIRED"
    elif region_ssim > PARTIAL_THRESHOLD:
        verdict = "PARTIAL"
    else:
        verdict = "UNREPAIRED"

    logger.info(
        "Verification %s: ssim=%.4f, region_ssim=%.4f → %s",
        pothole_uuid, ssim_score, region_ssim, verdict,
    )

    return {
        "ssim": round(ssim_score, 4),
        "region_ssim": round(region_ssim, 4),
        "verdict": verdict,
        "diff_s3": diff_s3,
    }


async def loop_closure_verification(
    pothole_uuid: str,
    new_image_path: str,
    before_image_s3: str,
    pothole_mask: list | None = None,
    pothole: dict | None = None,
    citizen_phones: list[str] | None = None,
) -> dict:
    """
    Full loop-closure verification combining AI (SSIM) + Social Audit.

    This is the "harder problem" solution — ensuring repair claims
    are verified through dual-layer accountability:
        Layer 1: AI-based SSIM image comparison
        Layer 2: Citizen Social Audit (WhatsApp polls)

    Args:
        pothole_uuid: pothole UUID
        new_image_path: local path to new scan image
        before_image_s3: S3 key of original detection image
        pothole_mask: optional YOLO mask polygon
        pothole: full pothole record (for social audit messaging)
        citizen_phones: phone numbers for social audit polls

    Returns:
        {
            'ai_verification': dict,    # SSIM results
            'social_audit': dict,       # Social Audit record
            'loop_closure_verdict': str, # Combined verdict
        }
    """
    # Layer 1: AI verification (SSIM)
    ai_result = verify_repair_production(
        pothole_uuid, new_image_path, before_image_s3, pothole_mask
    )

    # Layer 2: Initiate Social Audit
    social_audit_record = None
    if pothole and citizen_phones:
        try:
            from app.services.social_audit import initiate_social_audit

            social_audit_record = await initiate_social_audit(
                pothole=pothole,
                ai_verdict=ai_result["verdict"],
                ai_ssim_score=ai_result["ssim"],
                citizen_phones=citizen_phones,
            )
        except Exception as e:
            logger.error("Social audit initiation failed: %s", e)

    result = {
        "ai_verification": ai_result,
        "social_audit": (
            social_audit_record.to_dict()
            if social_audit_record
            else {"status": "not_initiated"}
        ),
        "loop_closure_verdict": (
            social_audit_record.loop_closure_verdict.value
            if social_audit_record and social_audit_record.loop_closure_verdict
            else ai_result["verdict"].lower()
        ),
    }

    logger.info(
        "Loop closure %s: ai=%s, social_audit=%s",
        pothole_uuid,
        ai_result["verdict"],
        result["loop_closure_verdict"],
    )

    return result
