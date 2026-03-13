# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Data Sovereignty & Security Framework
# Ensures CCTV feeds and citizen data comply with government
# data residency requirements (NIC SDC / MeghRaj GI Cloud)
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

import logging
from datetime import datetime
from enum import Enum
from typing import Optional

from app.config import settings

logger = logging.getLogger("apis.data_sovereignty")


# ── Data Classification Levels ────────────────────────────────
class DataClassification(str, Enum):
    """
    Government data classification per MeitY guidelines
    and NDSAP (National Data Sharing and Accessibility Policy).
    """
    PUBLIC = "public"              # Aggregated statistics, anonymized reports
    INTERNAL = "internal"          # Internal system logs, pipeline metadata
    RESTRICTED = "restricted"      # CCTV feeds, raw satellite imagery
    CONFIDENTIAL = "confidential"  # Citizen PII, government credentials


# ── Approved Storage Zones ────────────────────────────────────
APPROVED_ZONES = {
    "nic-sdc-raipur": {
        "name": "NIC State Data Centre — Raipur",
        "provider": "National Informatics Centre",
        "certification": "ISO 27001, MeitY Empanelled",
        "region": "Chhattisgarh",
        "aws_region": "ap-south-1",
    },
    "nic-sdc-delhi": {
        "name": "NIC National Data Centre — Delhi",
        "provider": "National Informatics Centre",
        "certification": "ISO 27001, Tier-IV",
        "region": "Delhi",
        "aws_region": "ap-south-1",
    },
    "meghraj-gi-cloud": {
        "name": "MeghRaj Government of India Cloud",
        "provider": "MeitY / NIC",
        "certification": "GI Cloud Policy Compliant",
        "region": "India",
        "aws_region": "ap-south-1",
    },
    "cg-swan": {
        "name": "Chhattisgarh State Wide Area Network",
        "provider": "CHIPS / NIC CG",
        "certification": "State IT Policy Compliant",
        "region": "Chhattisgarh",
        "aws_region": "ap-south-1",
    },
}

# ── Retention Policies (days) ─────────────────────────────────
RETENTION_POLICIES = {
    "cctv_raw_frames": 90,          # Raw CCTV frames: 90 days
    "satellite_imagery": 365,       # Satellite tiles: 1 year
    "detection_results": 1825,      # Detection records: 5 years
    "complaint_documents": 2555,    # Complaints & work orders: 7 years
    "citizen_pii": 365,             # Citizen data: 1 year post-resolution
    "system_logs": 180,             # System logs: 6 months
    "audit_trail": 3650,            # Audit trails: 10 years
}


class DataResidencyPolicy:
    """
    Enforces data residency, classification, and retention
    policies per government compliance requirements.
    """

    def __init__(self):
        self.active_zone = settings.DATA_RESIDENCY_ZONE
        self.approved_regions = settings.APPROVED_STORAGE_REGIONS

    def classify_data(self, data_type: str, source: str = "") -> DataClassification:
        """
        Classify data based on type and source.

        Args:
            data_type: e.g., 'cctv_frame', 'satellite_tile', 'citizen_report'
            source: data source identifier

        Returns:
            DataClassification enum value
        """
        classification_map = {
            # CCTV data — RESTRICTED (national highway surveillance)
            "cctv_frame": DataClassification.RESTRICTED,
            "cctv_video": DataClassification.RESTRICTED,
            "cctv_metadata": DataClassification.RESTRICTED,

            # Satellite data — RESTRICTED (Copernicus license terms)
            "satellite_tile": DataClassification.RESTRICTED,
            "sar_data": DataClassification.RESTRICTED,

            # Detection results — INTERNAL
            "detection_result": DataClassification.INTERNAL,
            "risk_score": DataClassification.INTERNAL,
            "pothole_record": DataClassification.INTERNAL,

            # Citizen data — CONFIDENTIAL (PII)
            "citizen_report": DataClassification.CONFIDENTIAL,
            "citizen_phone": DataClassification.CONFIDENTIAL,
            "citizen_verification": DataClassification.CONFIDENTIAL,

            # Complaints — INTERNAL (government correspondence)
            "complaint_letter": DataClassification.INTERNAL,
            "work_order": DataClassification.INTERNAL,
            "escalation_record": DataClassification.INTERNAL,

            # Analytics — PUBLIC (aggregated, anonymized)
            "analytics_summary": DataClassification.PUBLIC,
            "stretch_risk_report": DataClassification.PUBLIC,
            "monthly_trend": DataClassification.PUBLIC,
        }

        classification = classification_map.get(
            data_type, DataClassification.INTERNAL
        )

        logger.debug(
            "Data classified: type=%s, source=%s → %s",
            data_type, source, classification.value,
        )
        return classification

    def validate_storage_endpoint(
        self,
        s3_bucket: str,
        aws_region: str,
        data_type: str = "",
    ) -> dict:
        """
        Validate that a storage endpoint meets data residency requirements.

        Returns:
            {
                'compliant': bool,
                'zone': str,
                'classification': str,
                'violations': list[str],
            }
        """
        violations = []
        classification = self.classify_data(data_type)

        # Check if region is in approved list
        if aws_region not in self.approved_regions:
            violations.append(
                f"AWS region '{aws_region}' not in approved list: "
                f"{self.approved_regions}. "
                f"Data must reside within Indian sovereign territory "
                f"(MeitY Data Localisation Policy)."
            )

        # RESTRICTED and CONFIDENTIAL data must be in NIC SDC
        if classification in (
            DataClassification.RESTRICTED,
            DataClassification.CONFIDENTIAL,
        ):
            zone_info = APPROVED_ZONES.get(self.active_zone, {})
            if zone_info.get("aws_region") != aws_region:
                violations.append(
                    f"{classification.value.upper()} data must be stored in "
                    f"the designated SDC zone: {self.active_zone}. "
                    f"Current target region: {aws_region}."
                )

        compliant = len(violations) == 0

        if not compliant:
            logger.warning(
                "Data residency violation: bucket=%s, region=%s, "
                "classification=%s, violations=%s",
                s3_bucket, aws_region, classification.value, violations,
            )

        return {
            "compliant": compliant,
            "zone": self.active_zone,
            "zone_info": APPROVED_ZONES.get(self.active_zone, {}),
            "classification": classification.value,
            "violations": violations,
            "checked_at": datetime.now().isoformat(),
        }

    def get_retention_days(self, data_type: str) -> int:
        """Get retention period in days for a data type."""
        return RETENTION_POLICIES.get(data_type, 365)

    def generate_compliance_report(self) -> dict:
        """
        Generate a data residency compliance summary report.

        Useful for audit submissions and government reviews.
        """
        zone_info = APPROVED_ZONES.get(self.active_zone, {})

        return {
            "report_title": "APIS v5.0 — Data Residency Compliance Report",
            "generated_at": datetime.now().isoformat(),
            "generated_by": "APIS Data Sovereignty Module",
            "active_zone": {
                "id": self.active_zone,
                **zone_info,
            },
            "approved_regions": self.approved_regions,
            "data_classification_policy": {
                level.value: {
                    "description": _classification_description(level),
                    "storage_requirement": _storage_requirement(level),
                    "encryption": _encryption_requirement(level),
                    "access_control": _access_control(level),
                }
                for level in DataClassification
            },
            "retention_policies": {
                k: f"{v} days ({v // 365} years, {(v % 365) // 30} months)"
                for k, v in RETENTION_POLICIES.items()
            },
            "compliance_standards": [
                "MeitY Data Localisation Policy 2024",
                "National Data Sharing and Accessibility Policy (NDSAP)",
                "IT Act 2000, Section 43A — Sensitive Personal Data",
                "ISO 27001:2013 — Information Security Management",
                "CERT-In Cybersecurity Directives 2022",
                "NIC Cloud Services Policy — MeghRaj GI Cloud",
            ],
            "cctv_data_handling": {
                "classification": settings.CCTV_DATA_CLASSIFICATION,
                "source": "NHAI ATMS — National Highway CCTV Network",
                "storage": f"NIC SDC {zone_info.get('region', 'Chhattisgarh')}",
                "encryption": "AES-256 at rest, TLS 1.3 in transit",
                "retention": f"{RETENTION_POLICIES['cctv_raw_frames']} days",
                "access": "Role-based — authorized APIS service accounts only",
                "note": (
                    "All CCTV frames are processed in-situ within the SDC. "
                    "Only detection metadata (coordinates, severity) leaves "
                    "the secure zone. Raw frames are never transmitted externally."
                ),
            },
        }


# ── Module-level singleton ────────────────────────────────────
_policy: Optional[DataResidencyPolicy] = None


def get_data_residency_policy() -> DataResidencyPolicy:
    """Get or create the data residency policy singleton."""
    global _policy
    if _policy is None:
        _policy = DataResidencyPolicy()
    return _policy


# ── Helper descriptions ───────────────────────────────────────
def _classification_description(level: DataClassification) -> str:
    return {
        DataClassification.PUBLIC: "Aggregated, anonymized data suitable for public release",
        DataClassification.INTERNAL: "System-internal data, not for public distribution",
        DataClassification.RESTRICTED: "Sensitive infrastructure data (CCTV, satellite)",
        DataClassification.CONFIDENTIAL: "Personally identifiable information (PII)",
    }[level]


def _storage_requirement(level: DataClassification) -> str:
    return {
        DataClassification.PUBLIC: "Any approved Indian cloud region",
        DataClassification.INTERNAL: "NIC SDC or MeghRaj GI Cloud",
        DataClassification.RESTRICTED: "NIC State Data Centre only",
        DataClassification.CONFIDENTIAL: "NIC SDC with additional access controls",
    }[level]


def _encryption_requirement(level: DataClassification) -> str:
    return {
        DataClassification.PUBLIC: "TLS 1.2+ in transit",
        DataClassification.INTERNAL: "AES-256 at rest, TLS 1.2+ in transit",
        DataClassification.RESTRICTED: "AES-256 at rest, TLS 1.3 in transit, key rotation 90 days",
        DataClassification.CONFIDENTIAL: "AES-256 at rest, TLS 1.3, field-level encryption, key rotation 30 days",
    }[level]


def _access_control(level: DataClassification) -> str:
    return {
        DataClassification.PUBLIC: "Open access",
        DataClassification.INTERNAL: "Service-account authenticated",
        DataClassification.RESTRICTED: "Role-based with audit logging",
        DataClassification.CONFIDENTIAL: "Multi-factor with mandatory audit trail",
    }[level]
