# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Gemini AI Complaint Letter Generator
# Section 8: Gemini 1.5 Pro letter generation with authority
#             routing, quality checks, JSON metadata extraction
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from app.config import settings

logger = logging.getLogger("apis.complaint_gen")


def _get_authority(risk_score: float, road: dict) -> dict:
    """Determine grievance authority based on risk score and highway type."""
    if risk_score >= 8.0:
        return {
            "name": "The Chairman",
            "org": "National Highways Authority of India",
            "addr": "G-5 & 6, Sector 10, Dwarka, New Delhi – 110 075",
            "cc": (
                "CC: Secretary, Ministry of Road Transport and Highways "
                "| Chief Engineer (NH), PWD Chhattisgarh"
            ),
        }
    elif risk_score >= 6.0:
        return {
            "name": "The Regional Officer",
            "org": "NHAI Regional Office, Raipur",
            "addr": "NHAI Regional Office, Raipur, Chhattisgarh",
            "cc": "CC: Divisional Engineer, NH-30 Division",
        }
    else:
        district = road.get("district", "Raipur")
        return {
            "name": "The Executive Engineer",
            "org": f"PWD Division, {district}",
            "addr": f"PWD Office, {district}, Chhattisgarh",
            "cc": "CC: NHAI Project Director, Raipur",
        }


async def generate_complaint_letter(
    pothole: dict,
    road: dict,
    weather: dict,
    accidents: int,
) -> dict:
    """
    Generate a formal complaint letter using Gemini 1.5 Pro.

    Args:
        pothole: full pothole record dict
        road: highway segment data
        weather: weather at detection point
        accidents: accident count within 1 km / 1 year

    Returns:
        {
            'letter': str,           # full letter text
            'metadata': dict,        # parsed JSON metadata
            'pdf_s3_url': str | None # PDF URL if generated
        }
    """
    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set — using template letter")
        return _generate_template_letter(pothole, road, weather, accidents)

    import google.generativeai as genai

    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-pro")

    authority = _get_authority(pothole.get("risk_score", 5.0), road)
    sla_deadline = (datetime.now() + timedelta(days=30)).strftime("%d %B %Y")

    prompt = f"""
You are the Autonomous Pothole Intelligence System (APIS), a government-grade
automated road monitoring system deployed by CHIPS (Chhattisgarh Infotech
Promotion Society) under the AIML Hackathon PS-02 initiative.

Write a formal official complaint letter to be submitted to pgportal.gov.in
on behalf of APIS. The letter must conform to Indian government correspondence
standards (formal English, passive constructions where appropriate, Section/
Sub-section references to applicable Acts/Policies).

RECIPIENT:
  {authority['name']}
  {authority['org']}
  {authority['addr']}

POTHOLE FIELD DATA (do not alter or round these values):
  System Reference  : {pothole.get('uuid', 'N/A')}
  Highway           : {road.get('highway_id', 'NH-30')}, KM Marker {road.get('km_marker', 'N/A')}
  GPS (WGS84)       : {pothole.get('lat', 0):.6f}°N, {pothole.get('lon', 0):.6f}°E
  Severity Grade    : {pothole.get('severity', 'medium').upper()} (APIS Classification Scale)
  Risk Index        : {pothole.get('risk_score', 5.0)}/10.0 (Multi-factor accident risk)
  Pothole Area      : {pothole.get('area_sqm', 0):.2f} m²
  Estimated Depth   : {pothole.get('depth_cm', 0):.1f} cm
  Lane Position     : {pothole.get('lane_position', 'centre').upper()} lane
  First Detected    : {pothole.get('first_detected', datetime.now()).strftime('%d %B %Y, %H:%M IST') if isinstance(pothole.get('first_detected'), datetime) else pothole.get('first_detected', 'N/A')}
  Detection Method  : {pothole.get('source_primary', 'satellite').upper()} imagery
                      (Confidence: {pothole.get('confidence', 0.85):.1%})
  Accident History  : {accidents} road accidents recorded within 1 km in the past 12 months
                      (Source: iRAD/MoRTH accident database)
  Current Weather   : {weather.get('condition', 'N/A')}, Rainfall: {weather.get('rainfall_mm', 0)} mm
                      Cumulative 7-day rainfall: {weather.get('rainfall_7d_mm', 0)} mm
  Speed Limit       : {road.get('speed_limit_kmh', 80)} km/h at this section
  AADT              : {road.get('aadt', 5000):,} vehicles/day (Source: NHAI TIS)

LETTER REQUIREMENTS:
  1. Open with: "Sub: Urgent Representation Regarding {pothole.get('severity', 'medium').title()}-
     Grade Road Hazard on {road.get('highway_id', 'NH-30')} at KM {road.get('km_marker', 'N/A')} —
     Immediate Repair and Safety Intervention Requested — APIS Ref: {pothole.get('uuid', 'N/A')}"
  2. Cite NHAI Grievance Redressal Policy 2022 and the 30-day SLA for NH repairs
  3. Reference the Motor Vehicles (Amendment) Act 2019, Section 198A
  4. State that this complaint was auto-generated and auto-filed by an AI system
  5. Mention that the system will auto-escalate to NHAI HQ and MoRTH if not resolved by {sla_deadline}
  6. Demand: (a) immediate temporary patching within 72 hours,
     (b) permanent repair within 30 days, (c) acknowledgement with repair work order number
  7. Length: 300–380 words
  8. End with:
       Yours faithfully,
       Autonomous Pothole Intelligence System (APIS)
       Deployed by: CHIPS, Chhattisgarh Infotech Promotion Society
       System Reference: {pothole.get('uuid', 'N/A')}
       {authority['cc']}

After the letter, output a valid JSON block (no markdown fences) with:
{{
  "subject_line": "full subject line",
  "priority": "URGENT|HIGH|NORMAL",
  "authority_name": "{authority['name']}",
  "authority_org": "{authority['org']}",
  "sla_deadline_date": "{(datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')}",
  "escalation_date": "{(datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')}",
  "word_count": integer,
  "hindi_summary": "50-word Hindi summary of this complaint",
  "section_198a_applicable": true,
  "immediate_patching_demanded": true
}}
"""

    try:
        response = model.generate_content(prompt)
        raw_text = response.text

        # Split letter from JSON
        letter_end = raw_text.rfind("{")
        letter = raw_text[:letter_end].strip()
        json_str = raw_text[letter_end:]

        # Quality checks
        uuid = pothole.get("uuid", "")
        assert uuid in letter, f"UUID {uuid} missing from letter"

        word_count = len(letter.split())
        if word_count < 200 or word_count > 500:
            logger.warning("Letter word count %d outside ideal range", word_count)

        metadata = json.loads(json_str)

        # Generate PDF
        from app.services.pdf_gen import generate_letterhead_pdf

        pdf_s3 = generate_letterhead_pdf(letter, metadata, pothole, road)

        return {
            "letter": letter,
            "metadata": metadata,
            "pdf_s3_url": pdf_s3,
        }

    except Exception as e:
        logger.error("Gemini complaint generation failed: %s", e)
        return _generate_template_letter(pothole, road, weather, accidents)


def _generate_template_letter(
    pothole: dict, road: dict, weather: dict, accidents: int,
) -> dict:
    """Fallback template letter when Gemini is unavailable."""
    authority = _get_authority(pothole.get("risk_score", 5.0), road)
    sla_deadline = (datetime.now() + timedelta(days=30)).strftime("%d %B %Y")

    letter = f"""To,
{authority['name']}
{authority['org']}
{authority['addr']}

Sub: Urgent Representation Regarding {pothole.get('severity', 'Medium').title()}-Grade Road Hazard on {road.get('highway_id', 'NH-30')} at KM {road.get('km_marker', 'N/A')} — Immediate Repair and Safety Intervention Requested — APIS Ref: {pothole.get('uuid', 'N/A')}

Respected Sir/Madam,

This is to bring to your notice a {pothole.get('severity', 'medium')}-grade pothole detected on {road.get('highway_id', 'NH-30')} at KM marker {road.get('km_marker', 'N/A')} (GPS: {pothole.get('lat', 0):.6f}°N, {pothole.get('lon', 0):.6f}°E) by the Autonomous Pothole Intelligence System (APIS).

The pothole has a risk index of {pothole.get('risk_score', 5.0)}/10.0, estimated area of {pothole.get('area_sqm', 0):.2f} m², and depth of {pothole.get('depth_cm', 0):.1f} cm. It was detected via {pothole.get('source_primary', 'satellite').upper()} imagery with {pothole.get('confidence', 0.85):.1%} confidence.

{accidents} road accidents have been recorded within 1 km of this location in the past 12 months. Current weather conditions show {weather.get('condition', 'N/A')} with {weather.get('rainfall_7d_mm', 0)} mm rainfall in the past 7 days.

As per the NHAI Grievance Redressal Policy 2022 and the Motor Vehicles (Amendment) Act 2019, Section 198A, immediate action is demanded:
(a) Temporary patching within 72 hours
(b) Permanent repair within 30 days
(c) Acknowledgement with repair work order number

This complaint is auto-generated and filed by the APIS system. If unresolved by {sla_deadline}, it will be auto-escalated to NHAI National HQ and MoRTH.

Yours faithfully,
Autonomous Pothole Intelligence System (APIS)
Deployed by: CHIPS, Chhattisgarh Infotech Promotion Society
System Reference: {pothole.get('uuid', 'N/A')}
{authority['cc']}
"""

    metadata = {
        "subject_line": f"Pothole on {road.get('highway_id', 'NH-30')} KM {road.get('km_marker', 'N/A')}",
        "priority": "URGENT" if pothole.get("risk_score", 5) >= 8 else "HIGH",
        "authority_name": authority["name"],
        "authority_org": authority["org"],
        "sla_deadline_date": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
        "escalation_date": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
        "word_count": len(letter.split()),
        "hindi_summary": "सड़क पर गड्ढा पाया गया है। कृपया तत्काल मरम्मत करें।",
        "section_198a_applicable": True,
        "immediate_patching_demanded": True,
    }

    return {"letter": letter, "metadata": metadata, "pdf_s3_url": None}
