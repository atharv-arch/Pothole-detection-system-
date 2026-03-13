# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Standardized Work Order Generator
# Generates actionable repair work orders with material BoQ,
# cost estimates, and contractor instructions based on IRC/CPWD
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

import logging
import math
import os
from datetime import date, datetime, timedelta
from typing import Optional

from app.config import settings

logger = logging.getLogger("apis.work_order")

# ── IRC / CPWD Material Constants ─────────────────────────────
# Density: IRC:SP:77-2008 Table 4.1
BITUMINOUS_MIX_DENSITY_KG_M3 = 2350    # Dense Bituminous Macadam (DBM)
TACK_COAT_RATE_KG_M2 = 0.25             # SS-1 emulsion
WMM_DENSITY_KG_M3 = 2200                # Wet Mix Macadam base

# CPWD SoR 2024 approximate rates (₹)
RATE_PATCHING_PER_SQM = 850              # Cold-mix patching per m²
RATE_MILL_AND_FILL_PER_SQM = 2200        # Mill & fill per m²
RATE_FULL_RECONSTRUCTION_PER_SQM = 4500  # Full depth reconstruction per m²
RATE_BITUMINOUS_MIX_PER_M3 = 12500       # DBM per m³
RATE_WMM_PER_M3 = 4200                   # WMM base per m³
RATE_TACK_COAT_PER_SQM = 45              # Tack coat per m²

# Repair method thresholds
PATCHING_MAX_DEPTH_CM = 5.0
PATCHING_MAX_AREA_SQM = 1.0
MILL_FILL_MAX_DEPTH_CM = 15.0
MILL_FILL_MAX_AREA_SQM = 5.0


def determine_repair_method(depth_cm: float, area_sqm: float) -> dict:
    """
    Determine repair method based on pothole dimensions using
    IRC:SP:77-2008 guidelines.

    Returns:
        {
            'method': str,
            'irc_reference': str,
            'description': str,
        }
    """
    if depth_cm <= PATCHING_MAX_DEPTH_CM and area_sqm <= PATCHING_MAX_AREA_SQM:
        return {
            "method": "COLD_MIX_PATCHING",
            "irc_reference": "IRC:SP:77-2008, Clause 5.2 — Spray Injection Patching",
            "description": (
                "Clean the pothole cavity, apply tack coat (SS-1 emulsion), "
                "fill with cold-mix bituminous material, and compact using "
                "vibratory plate compactor. Minimum 25mm overlay beyond edges."
            ),
        }
    elif depth_cm <= MILL_FILL_MAX_DEPTH_CM and area_sqm <= MILL_FILL_MAX_AREA_SQM:
        return {
            "method": "MILL_AND_FILL",
            "irc_reference": "IRC:SP:77-2008, Clause 5.3 — Semi-Permanent Repair",
            "description": (
                "Saw-cut square/rectangular boundary 150mm beyond visible distress. "
                "Remove deteriorated material to full depth. Apply tack coat, "
                "fill with hot-mix DBM in 50mm lifts, compact each lift to "
                "98% Marshall density. Surface with 40mm BC layer."
            ),
        }
    else:
        return {
            "method": "FULL_DEPTH_RECONSTRUCTION",
            "irc_reference": "IRC:SP:77-2008, Clause 5.4 — Full Depth Repair",
            "description": (
                "Full pavement reconstruction required. Excavate to subgrade, "
                "compact subgrade to 97% MDD. Lay 200mm WMM base, 100mm DBM "
                "binder course, and 40mm BC wearing course. Compact each layer "
                "per IRC:SP:16 specifications."
            ),
        }


def compute_material_boq(
    depth_cm: float,
    area_sqm: float,
    repair_method: str,
) -> list[dict]:
    """
    Compute Bill of Quantities (BoQ) for repair materials.

    Uses IRC:SP:77-2008 density constants and CPWD SoR 2024 rates.

    Returns list of material items with quantity, unit, and cost.
    """
    depth_m = depth_cm / 100.0
    volume_m3 = area_sqm * depth_m

    # Add 15% wastage factor per IRC guidelines
    volume_with_wastage = volume_m3 * 1.15

    boq = []

    if repair_method == "COLD_MIX_PATCHING":
        boq = [
            {
                "item": "Cold-Mix Bituminous Material",
                "quantity": round(volume_with_wastage * BITUMINOUS_MIX_DENSITY_KG_M3, 1),
                "unit": "kg",
                "rate_inr": RATE_BITUMINOUS_MIX_PER_M3,
                "rate_unit": "per m³",
                "cost_inr": round(volume_with_wastage * RATE_BITUMINOUS_MIX_PER_M3, 2),
            },
            {
                "item": "Tack Coat (SS-1 Emulsion)",
                "quantity": round(area_sqm * TACK_COAT_RATE_KG_M2, 2),
                "unit": "kg",
                "rate_inr": RATE_TACK_COAT_PER_SQM,
                "rate_unit": "per m²",
                "cost_inr": round(area_sqm * RATE_TACK_COAT_PER_SQM, 2),
            },
        ]

    elif repair_method == "MILL_AND_FILL":
        # Extended area (150mm beyond visible distress)
        extended_area = area_sqm * 1.3
        boq = [
            {
                "item": "Dense Bituminous Macadam (DBM)",
                "quantity": round(volume_with_wastage * BITUMINOUS_MIX_DENSITY_KG_M3, 1),
                "unit": "kg",
                "rate_inr": RATE_BITUMINOUS_MIX_PER_M3,
                "rate_unit": "per m³",
                "cost_inr": round(volume_with_wastage * RATE_BITUMINOUS_MIX_PER_M3, 2),
            },
            {
                "item": "Bituminous Concrete (BC) Wearing Course (40mm)",
                "quantity": round(extended_area * 0.04 * BITUMINOUS_MIX_DENSITY_KG_M3, 1),
                "unit": "kg",
                "rate_inr": RATE_BITUMINOUS_MIX_PER_M3,
                "rate_unit": "per m³",
                "cost_inr": round(extended_area * 0.04 * RATE_BITUMINOUS_MIX_PER_M3, 2),
            },
            {
                "item": "Tack Coat (SS-1 Emulsion)",
                "quantity": round(extended_area * TACK_COAT_RATE_KG_M2, 2),
                "unit": "kg",
                "rate_inr": RATE_TACK_COAT_PER_SQM,
                "rate_unit": "per m²",
                "cost_inr": round(extended_area * RATE_TACK_COAT_PER_SQM, 2),
            },
        ]

    elif repair_method == "FULL_DEPTH_RECONSTRUCTION":
        extended_area = area_sqm * 1.5
        boq = [
            {
                "item": "Wet Mix Macadam (WMM) Base (200mm)",
                "quantity": round(extended_area * 0.20 * WMM_DENSITY_KG_M3, 1),
                "unit": "kg",
                "rate_inr": RATE_WMM_PER_M3,
                "rate_unit": "per m³",
                "cost_inr": round(extended_area * 0.20 * RATE_WMM_PER_M3, 2),
            },
            {
                "item": "Dense Bituminous Macadam (DBM) Binder (100mm)",
                "quantity": round(extended_area * 0.10 * BITUMINOUS_MIX_DENSITY_KG_M3, 1),
                "unit": "kg",
                "rate_inr": RATE_BITUMINOUS_MIX_PER_M3,
                "rate_unit": "per m³",
                "cost_inr": round(extended_area * 0.10 * RATE_BITUMINOUS_MIX_PER_M3, 2),
            },
            {
                "item": "Bituminous Concrete (BC) Wearing Course (40mm)",
                "quantity": round(extended_area * 0.04 * BITUMINOUS_MIX_DENSITY_KG_M3, 1),
                "unit": "kg",
                "rate_inr": RATE_BITUMINOUS_MIX_PER_M3,
                "rate_unit": "per m³",
                "cost_inr": round(extended_area * 0.04 * RATE_BITUMINOUS_MIX_PER_M3, 2),
            },
            {
                "item": "Tack Coat (SS-1 Emulsion)",
                "quantity": round(extended_area * TACK_COAT_RATE_KG_M2 * 2, 2),
                "unit": "kg",
                "rate_inr": RATE_TACK_COAT_PER_SQM,
                "rate_unit": "per m²",
                "cost_inr": round(extended_area * 2 * RATE_TACK_COAT_PER_SQM, 2),
            },
        ]

    return boq


def generate_work_order(pothole: dict, road: dict) -> dict:
    """
    Generate a complete standardized repair work order.

    Args:
        pothole: full pothole record
        road: highway segment data

    Returns:
        {
            'work_order_number': str,
            'pothole_uuid': str,
            'location': dict,
            'dimensions': dict,
            'repair_method': dict,
            'material_boq': list[dict],
            'total_cost_inr': float,
            'sla_deadline': str,
            'instructions': str,
            'generated_at': str,
        }
    """
    depth_cm = pothole.get("depth_cm", 5.0) or 5.0
    area_sqm = pothole.get("area_sqm", 0.5) or 0.5
    depth_m = depth_cm / 100.0
    volume_m3 = round(area_sqm * depth_m, 4)

    # Determine repair method
    repair = determine_repair_method(depth_cm, area_sqm)

    # Compute BoQ
    boq = compute_material_boq(depth_cm, area_sqm, repair["method"])

    # Total cost
    total_cost = sum(item["cost_inr"] for item in boq)
    # Add 18% GST + 5% contingency
    total_with_overhead = round(total_cost * 1.18 * 1.05, 2)

    # Work order number
    today = date.today()
    wo_number = (
        f"WO-{road.get('highway_id', 'NH30').replace('-', '')}-"
        f"KM{pothole.get('km_marker', 0):.0f}-"
        f"{today.strftime('%Y%m%d')}-"
        f"{pothole.get('uuid', 'UNKNOWN')[-6:]}"
    )

    # SLA deadline based on severity
    severity = pothole.get("severity", "medium")
    sla_days = {"critical": 3, "high": 7, "medium": 15, "low": 30}.get(severity, 15)
    sla_deadline = (datetime.now() + timedelta(days=sla_days)).strftime("%Y-%m-%d")

    work_order = {
        "work_order_number": wo_number,
        "pothole_uuid": pothole.get("uuid", "N/A"),
        "location": {
            "highway_id": road.get("highway_id", "NH-30"),
            "km_marker": pothole.get("km_marker"),
            "district": road.get("district", "Raipur"),
            "gps_lat": pothole.get("lat"),
            "gps_lon": pothole.get("lon"),
            "lane_position": pothole.get("lane_position", "centre"),
        },
        "dimensions": {
            "area_sqm": area_sqm,
            "depth_cm": depth_cm,
            "volume_m3": volume_m3,
            "severity": severity,
        },
        "repair_method": repair,
        "material_boq": boq,
        "cost_summary": {
            "material_cost_inr": round(total_cost, 2),
            "gst_18_percent": round(total_cost * 0.18, 2),
            "contingency_5_percent": round(total_cost * 1.18 * 0.05, 2),
            "total_estimated_cost_inr": total_with_overhead,
        },
        "sla_deadline": sla_deadline,
        "sla_days": sla_days,
        "instructions": (
            f"1. Mobilize crew and equipment within 24 hours of work order receipt.\n"
            f"2. Set up traffic management per IRC:SP:55 before commencing work.\n"
            f"3. Execute repair as per {repair['irc_reference']}.\n"
            f"4. {repair['description']}\n"
            f"5. Conduct quality checks: Marshall stability, compaction density.\n"
            f"6. Upload post-repair photographs to APIS system for AI verification.\n"
            f"7. Complete work by SLA deadline: {sla_deadline}.\n"
            f"8. Submit measurement book entry and completion certificate."
        ),
        "generated_at": datetime.now().isoformat(),
        "generated_by": "APIS v5.0 — Autonomous Pothole Intelligence System",
        "reference_standards": [
            "IRC:SP:77-2008 — Manual for Maintenance of Bituminous Surfaces",
            "IRC:SP:16 — Surface Evenness of Highway Pavements",
            "IRC:SP:55 — Traffic Safety at Work Zones",
            "CPWD SoR 2024 — Schedule of Rates",
            "MORT&H 5th Revision — Specifications for Road and Bridge Works",
        ],
    }

    logger.info(
        "Work order generated: %s — method=%s, cost=₹%.2f",
        wo_number, repair["method"], total_with_overhead,
    )

    return work_order


def generate_work_order_pdf(work_order: dict) -> Optional[str]:
    """
    Generate a work order PDF using ReportLab.

    Returns S3 URL of the uploaded PDF, or local path if S3 unavailable.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
        )

        pdf_path = os.path.join(
            os.environ.get("TEMP", "/tmp"),
            f"{work_order['work_order_number']}.pdf",
        )

        doc = SimpleDocTemplate(
            pdf_path, pagesize=A4,
            leftMargin=20 * mm, rightMargin=20 * mm,
            topMargin=20 * mm, bottomMargin=20 * mm,
        )
        styles = getSampleStyleSheet()
        elements = []

        # Title
        title_style = ParagraphStyle(
            "WOTitle", fontSize=16, fontName="Helvetica-Bold",
            spaceAfter=6, alignment=1,
        )
        elements.append(Paragraph("STANDARDIZED REPAIR WORK ORDER", title_style))
        elements.append(Paragraph(
            "Autonomous Pothole Intelligence System (APIS) — CHIPS, Chhattisgarh",
            ParagraphStyle("Sub", fontSize=9, alignment=1, spaceAfter=12),
        ))
        elements.append(Spacer(1, 6))

        # Work Order Details
        wo = work_order
        loc = wo["location"]
        dim = wo["dimensions"]

        details = [
            ["Work Order No.", wo["work_order_number"]],
            ["APIS Reference", wo["pothole_uuid"]],
            ["Highway", f"{loc['highway_id']} — KM {loc['km_marker']}"],
            ["District", loc["district"]],
            ["GPS", f"{loc.get('gps_lat', 'N/A')}°N, {loc.get('gps_lon', 'N/A')}°E"],
            ["Lane", loc.get("lane_position", "N/A").upper()],
            ["Area", f"{dim['area_sqm']} m²"],
            ["Depth", f"{dim['depth_cm']} cm"],
            ["Volume", f"{dim['volume_m3']} m³"],
            ["Severity", dim["severity"].upper()],
            ["Repair Method", wo["repair_method"]["method"].replace("_", " ")],
            ["IRC Reference", wo["repair_method"]["irc_reference"]],
            ["SLA Deadline", f"{wo['sla_deadline']} ({wo['sla_days']} days)"],
        ]

        detail_table = Table(details, colWidths=[45 * mm, 120 * mm])
        detail_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (0, -1), colors.Color(0.93, 0.93, 0.95)),
        ]))
        elements.append(detail_table)
        elements.append(Spacer(1, 10))

        # Material BoQ Table
        elements.append(Paragraph(
            "BILL OF QUANTITIES (BoQ)",
            ParagraphStyle("BOQ", fontSize=12, fontName="Helvetica-Bold", spaceAfter=6),
        ))

        boq_header = ["Material", "Quantity", "Unit", "Rate (₹)", "Cost (₹)"]
        boq_rows = [boq_header]
        for item in wo["material_boq"]:
            boq_rows.append([
                item["item"],
                f"{item['quantity']:,.1f}",
                item["unit"],
                f"₹{item['rate_inr']:,.0f} {item['rate_unit']}",
                f"₹{item['cost_inr']:,.2f}",
            ])

        # Cost summary rows
        cs = wo["cost_summary"]
        boq_rows.append(["", "", "", "Material Subtotal", f"₹{cs['material_cost_inr']:,.2f}"])
        boq_rows.append(["", "", "", "GST (18%)", f"₹{cs['gst_18_percent']:,.2f}"])
        boq_rows.append(["", "", "", "Contingency (5%)", f"₹{cs['contingency_5_percent']:,.2f}"])
        boq_rows.append(["", "", "", "TOTAL ESTIMATED", f"₹{cs['total_estimated_cost_inr']:,.2f}"])

        boq_table = Table(
            boq_rows,
            colWidths=[55 * mm, 22 * mm, 15 * mm, 40 * mm, 33 * mm],
        )
        boq_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.2, 0.3, 0.5)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("FONTNAME", (3, -1), (-1, -1), "Helvetica-Bold"),
            ("BACKGROUND", (3, -1), (-1, -1), colors.Color(0.93, 0.95, 0.93)),
        ]))
        elements.append(boq_table)
        elements.append(Spacer(1, 10))

        # Instructions
        elements.append(Paragraph(
            "CONTRACTOR INSTRUCTIONS",
            ParagraphStyle("Inst", fontSize=12, fontName="Helvetica-Bold", spaceAfter=6),
        ))
        for line in wo["instructions"].split("\n"):
            elements.append(Paragraph(
                line.strip(),
                ParagraphStyle("InstLine", fontSize=9, spaceAfter=3),
            ))

        doc.build(elements)

        # Upload to S3
        try:
            from app.services.s3 import s3_upload
            s3_key = f"work_orders/{wo['work_order_number']}.pdf"
            s3_upload(pdf_path, s3_key)
            logger.info("Work order PDF uploaded: %s", s3_key)
            return s3_key
        except Exception:
            logger.warning("S3 upload failed — returning local path")
            return pdf_path

    except Exception as e:
        logger.error("Work order PDF generation failed: %s", e)
        return None
