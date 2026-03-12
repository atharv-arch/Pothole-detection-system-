# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — PDF Letterhead Generator (ReportLab)
# Section 8: A4 complaint letter with header, reference table,
#             body text, and pothole image
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime

from app.services.s3 import s3_upload

logger = logging.getLogger("apis.pdf_gen")


def generate_letterhead_pdf(
    letter: str,
    metadata: dict,
    pothole: dict,
    road: dict,
) -> str | None:
    """
    Generate a formal A4 PDF complaint letter with APIS letterhead.

    Returns:
        S3 URL of the uploaded PDF, or None on failure.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        )
    except ImportError:
        logger.error("reportlab not installed — cannot generate PDF")
        return None

    uuid = pothole.get("uuid", "UNKNOWN")
    path = os.path.join(tempfile.gettempdir(), f"{uuid}_complaint.pdf")

    try:
        doc = SimpleDocTemplate(
            path,
            pagesize=A4,
            topMargin=1.5 * cm,
            bottomMargin=1.5 * cm,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
        )
        styles = getSampleStyleSheet()
        content = []

        # ── Header ─────────────────────────────────────────
        header_style = ParagraphStyle(
            "APISHeader",
            parent=styles["Heading1"],
            fontSize=14,
            textColor=colors.HexColor("#0A1628"),
            spaceAfter=4,
        )
        sub_style = ParagraphStyle(
            "APISSubHeader",
            parent=styles["Normal"],
            fontSize=9,
            textColor=colors.HexColor("#4A5568"),
            spaceAfter=8,
        )

        content.append(
            Paragraph(
                "AUTONOMOUS POTHOLE INTELLIGENCE SYSTEM (APIS)",
                header_style,
            )
        )
        content.append(
            Paragraph(
                "Deployed by CHIPS — Chhattisgarh Infotech Promotion Society",
                sub_style,
            )
        )
        content.append(Spacer(1, 0.3 * cm))

        # ── Reference Box ──────────────────────────────────
        ref_data = [
            ["System Reference", uuid],
            ["Highway", f"{road.get('highway_id', 'NH-30')}, KM {road.get('km_marker', 'N/A')}"],
            ["GPS", f"{pothole.get('lat', 0):.6f}°N, {pothole.get('lon', 0):.6f}°E"],
            [
                "Risk Score",
                f"{pothole.get('risk_score', 0)}/10.0 ({pothole.get('severity', 'N/A').upper()})",
            ],
            ["Filed On", datetime.now().strftime("%d %B %Y")],
        ]

        table = Table(ref_data, colWidths=[5 * cm, 10 * cm])
        table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0A1628")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E8F0FE")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        content.append(table)
        content.append(Spacer(1, 0.5 * cm))

        # ── Letter Body ────────────────────────────────────
        body_style = ParagraphStyle(
            "LetterBody",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
            spaceAfter=6,
        )

        for para in letter.split("\n\n"):
            para_text = para.strip()
            if para_text:
                content.append(Paragraph(para_text, body_style))
                content.append(Spacer(1, 0.15 * cm))

        # ── Build PDF ──────────────────────────────────────
        doc.build(content)

        # Upload to S3
        s3_key = f"complaints/{uuid}_letter.pdf"
        s3_url = s3_upload(path, s3_key)

        logger.info("PDF generated and uploaded: %s", s3_url)
        return s3_url

    except Exception as e:
        logger.error("PDF generation failed: %s", e)
        return None
    finally:
        if os.path.exists(path):
            os.remove(path)
