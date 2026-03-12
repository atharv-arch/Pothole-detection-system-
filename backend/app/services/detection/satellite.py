# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Sentinel-2 Satellite Data Pipeline
# Section 2: ESA Copernicus Hub download, band extraction, caching
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from app.config import settings
from app.services.s3 import s3_download, s3_exists, s3_upload

logger = logging.getLogger("apis.satellite")


class SentinelDownloader:
    """Manages Sentinel-2 L2A tile queries, downloads, and band extraction."""

    BANDS = ["B02", "B03", "B04", "B08"]  # Blue, Green, Red, NIR

    def __init__(self):
        self._api = None

    @property
    def api(self):
        if self._api is None:
            if not settings.COPERNICUS_USER:
                raise RuntimeError(
                    "COPERNICUS_USER not set — satellite downloads unavailable"
                )
            from sentinelsat import SentinelAPI

            self._api = SentinelAPI(
                settings.COPERNICUS_USER,
                settings.COPERNICUS_PASS,
                "https://scihub.copernicus.eu/dhus",
            )
        return self._api

    def query_nh30(
        self, days_back: int = 7, max_cloud: int = 20
    ) -> dict[str, Any]:
        """Query Sentinel-2 L2A products over NH-30 corridor."""
        from shapely.geometry import box

        nh30_bbox = box(
            settings.NH30_BBOX_SW_LON,
            settings.NH30_BBOX_SW_LAT,
            settings.NH30_BBOX_NE_LON,
            settings.NH30_BBOX_NE_LAT,
        )

        products = self.api.query(
            area=nh30_bbox.wkt,
            date=(f"NOW-{days_back}DAYS", "NOW"),
            platformname="Sentinel-2",
            producttype="S2MSI2A",
            cloudcoverpercentage=(0, max_cloud),
        )

        logger.info("Found %d Sentinel-2 products for NH-30", len(products))
        return products

    def has_new_tile(self, products: dict, last_scan_date: datetime) -> bool:
        """Check if any product is newer than the last scan."""
        if not products:
            return False
        latest = max(p["ingestiondate"] for p in products.values())
        return latest > last_scan_date

    def download_and_cache(self, products: dict) -> list[str]:
        """Download tiles to S3 if not already cached. Return local paths."""
        local_paths = []
        tmp_dir = tempfile.mkdtemp(prefix="sentinel_")

        for product_id, product_info in products.items():
            s3_key = f"sentinel2/{product_id}.zip"
            local_path = os.path.join(tmp_dir, f"{product_id}.zip")

            if not s3_exists(s3_key):
                logger.info("Downloading tile %s from ESA...", product_id)
                self.api.download(product_id, directory_path=tmp_dir)
                s3_upload(local_path, s3_key)
            else:
                logger.info("Tile %s cached in S3, downloading...", product_id)
                s3_download(s3_key, local_path)

            local_paths.append(local_path)

        return local_paths

    def extract_road_bands(
        self, product_path: str, road_buffer_geojson: dict
    ) -> np.ndarray:
        """Extract and stack B02/B03/B04/B08 bands cropped to road buffer."""
        import rasterio
        from rasterio.mask import mask as rio_mask

        bands = []
        transform = None

        for band_name in self.BANDS:
            band_file = self._find_band_file(product_path, band_name)
            if band_file is None:
                logger.error("Band %s not found in %s", band_name, product_path)
                continue

            with rasterio.open(band_file) as src:
                cropped, transform = rio_mask(
                    src, [road_buffer_geojson], crop=True
                )
                bands.append(cropped[0])  # squeeze band dimension

        if len(bands) != 4:
            raise ValueError(
                f"Expected 4 bands, got {len(bands)} from {product_path}"
            )

        # Stack to (H, W, 4) — BGRNIR
        stacked = np.stack(bands, axis=-1).astype(np.float32)
        logger.info(
            "Extracted road bands: shape=%s, transform=%s",
            stacked.shape, transform,
        )
        return stacked

    def _find_band_file(self, product_path: str, band_name: str) -> str | None:
        """Walk product directory to find the JP2 file for a given band."""
        product_dir = Path(product_path)
        if product_path.endswith(".zip"):
            import zipfile

            with zipfile.ZipFile(product_path, "r") as zf:
                zf.extractall(product_dir.parent)
            # Find extracted .SAFE directory
            safe_dirs = list(product_dir.parent.glob("*.SAFE"))
            product_dir = safe_dirs[0] if safe_dirs else product_dir.parent

        pattern = f"*_{band_name}_10m.jp2"
        matches = list(product_dir.rglob(pattern))
        if not matches:
            # Fallback: try without resolution suffix
            matches = list(product_dir.rglob(f"*_{band_name}.jp2"))
        return str(matches[0]) if matches else None


class SentinelSARDownloader:
    """Managed Sentinel-1 SAR (GRD/IW) for InSAR subsidence detection."""

    def __init__(self):
        self._api = None

    @property
    def api(self):
        if self._api is None:
            from sentinelsat import SentinelAPI

            self._api = SentinelAPI(
                settings.COPERNICUS_USER,
                settings.COPERNICUS_PASS,
                "https://scihub.copernicus.eu/dhus",
            )
        return self._api

    def query_nh30_sar(self, days_back: int = 14) -> dict[str, Any]:
        """Query Sentinel-1 GRD products for InSAR analysis."""
        from shapely.geometry import box

        nh30_bbox = box(
            settings.NH30_BBOX_SW_LON,
            settings.NH30_BBOX_SW_LAT,
            settings.NH30_BBOX_NE_LON,
            settings.NH30_BBOX_NE_LAT,
        )

        products = self.api.query(
            area=nh30_bbox.wkt,
            date=(f"NOW-{days_back}DAYS", "NOW"),
            platformname="Sentinel-1",
            producttype="GRD",
            polarisationmode="VV VH",
            sensoroperationalmode="IW",
        )

        logger.info("Found %d Sentinel-1 SAR products", len(products))
        return products

    def analyze_subsidence(
        self, pass1_path: str, pass2_path: str
    ) -> list[dict]:
        """
        Run differential InSAR analysis between two SAR passes.
        Returns list of subsidence points with displacement in mm.

        NOTE: Full InSAR processing requires ESA SNAP toolkit (snapista).
        This method outlines the pipeline — full implementation requires
        SNAP installation on the processing server.
        """
        logger.info(
            "InSAR analysis: %s vs %s", pass1_path, pass2_path
        )

        # Pipeline steps (SNAP Graph Builder):
        # 1. Apply orbit file correction
        # 2. Back-geocoding (coregister two passes)
        # 3. Interferogram formation
        # 4. Goldstein phase filtering
        # 5. Phase unwrapping (SNAPHU)
        # 6. Convert phase to displacement (mm)

        # Placeholder for SNAP/snapista integration
        # In production: snapista.Graph() → configure → run
        subsidence_points = []

        logger.warning(
            "Full InSAR processing requires SNAP toolkit — "
            "returning empty subsidence list until SNAP is configured"
        )

        return subsidence_points

    def classify_subsidence(self, displacement_mm: float) -> str:
        """Classify subsidence displacement into risk categories."""
        if displacement_mm > 5:
            return "SAR_PRECURSOR"  # high confidence
        elif displacement_mm >= 3:
            return "SAR_WATCH"  # monitor
        else:
            return "SAR_NONE"  # no action
