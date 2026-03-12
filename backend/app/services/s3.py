# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — S3 Storage Helpers
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger("apis.s3")

_client = None


def _get_client():
    global _client
    if _client is None:
        kwargs = {"region_name": settings.AWS_REGION}
        if settings.AWS_ACCESS_KEY_ID:
            kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
            kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
        _client = boto3.client("s3", **kwargs)
    return _client


def s3_upload(local_path: str, s3_key: str) -> str:
    """Upload a local file to S3 and return the S3 URI."""
    try:
        _get_client().upload_file(local_path, settings.S3_BUCKET_NAME, s3_key)
        s3_uri = f"s3://{settings.S3_BUCKET_NAME}/{s3_key}"
        logger.info("Uploaded %s → %s", local_path, s3_uri)
        return s3_uri
    except ClientError as e:
        logger.error("S3 upload failed: %s", e)
        raise


def s3_download(s3_key: str, local_path: str) -> str:
    """Download a file from S3 to a local path."""
    try:
        _get_client().download_file(settings.S3_BUCKET_NAME, s3_key, local_path)
        logger.info("Downloaded %s → %s", s3_key, local_path)
        return local_path
    except ClientError as e:
        logger.error("S3 download failed: %s", e)
        raise


def s3_download_temp(s3_key: str) -> str:
    """Download S3 file to a temp path and return it."""
    # Strip s3:// prefix if present
    if s3_key.startswith("s3://"):
        s3_key = s3_key.split("/", 3)[-1]  # remove bucket prefix too
    ext = Path(s3_key).suffix
    fd, tmp_path = tempfile.mkstemp(suffix=ext)
    os.close(fd)
    return s3_download(s3_key, tmp_path)


def s3_exists(s3_key: str) -> bool:
    """Check if a key exists in S3."""
    try:
        _get_client().head_object(Bucket=settings.S3_BUCKET_NAME, Key=s3_key)
        return True
    except ClientError:
        return False


def s3_save_frame(frame, camera_id: str) -> str:
    """Save an OpenCV frame to S3, return the S3 key."""
    import cv2
    from datetime import datetime

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    s3_key = f"cctv_frames/{camera_id}/{timestamp}.jpg"
    tmp = tempfile.mktemp(suffix=".jpg")
    cv2.imwrite(tmp, frame)
    s3_upload(tmp, s3_key)
    os.remove(tmp)
    return s3_key


def s3_save_image(image_array, s3_key: str) -> str:
    """Save a numpy array as image to S3."""
    import cv2

    tmp = tempfile.mktemp(suffix=".jpg")
    cv2.imwrite(tmp, image_array)
    result = s3_upload(tmp, s3_key)
    os.remove(tmp)
    return result


def s3_get_signed_url(s3_key: str, expiration: int = 3600) -> str:
    """Generate a pre-signed URL for an S3 object."""
    if s3_key.startswith("s3://"):
        parts = s3_key.replace("s3://", "").split("/", 1)
        s3_key = parts[1] if len(parts) > 1 else s3_key
    try:
        url = _get_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.S3_BUCKET_NAME, "Key": s3_key},
            ExpiresIn=expiration,
        )
        return url
    except ClientError as e:
        logger.error("Failed to generate signed URL: %s", e)
        return ""
