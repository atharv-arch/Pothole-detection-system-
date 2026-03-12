# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Complaints API Router
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import ComplaintResponse, EscalationResponse

router = APIRouter(prefix="/api/complaints", tags=["Complaints"])


@router.get("", response_model=list[ComplaintResponse])
async def list_complaints(
    status: Optional[str] = None,
    tier: Optional[int] = None,
    highway: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List all complaints with filtering."""
    query = """
        SELECT c.*, p.highway_id, p.km_marker, p.severity, p.risk_score
        FROM complaints c
        LEFT JOIN potholes p ON c.pothole_uuid = p.uuid
        WHERE 1=1
    """
    params = {}

    if status:
        query += " AND c.status = :status"
        params["status"] = status
    if tier:
        query += " AND c.tier = :tier"
        params["tier"] = tier
    if highway:
        query += " AND p.highway_id = :highway"
        params["highway"] = highway

    query += " ORDER BY c.filed_at DESC NULLS LAST LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset

    result = await db.execute(text(query), params)
    return [dict(row._mapping) for row in result.fetchall()]


@router.get("/{complaint_id}")
async def get_complaint(complaint_id: str, db: AsyncSession = Depends(get_db)):
    """Get single complaint with full details."""
    result = await db.execute(
        text("""
            SELECT c.*, p.highway_id, p.km_marker, p.severity, p.risk_score
            FROM complaints c
            LEFT JOIN potholes p ON c.pothole_uuid = p.uuid
            WHERE c.complaint_id = :cid
        """),
        {"cid": complaint_id},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Complaint not found")

    complaint = dict(row._mapping)

    # Fetch escalation log
    esc_result = await db.execute(
        text("""
            SELECT * FROM escalation_log
            WHERE complaint_id = :cid ORDER BY escalated_at
        """),
        {"cid": complaint_id},
    )
    complaint["escalations"] = [dict(e._mapping) for e in esc_result.fetchall()]

    # Generate signed URLs
    from app.services.s3 import s3_get_signed_url

    if complaint.get("letter_pdf_s3"):
        complaint["letter_pdf_url"] = s3_get_signed_url(complaint["letter_pdf_s3"])
    if complaint.get("confirmation_s3"):
        complaint["confirmation_url"] = s3_get_signed_url(complaint["confirmation_s3"])

    return complaint


@router.get("/escalations/all", response_model=list[EscalationResponse])
async def list_escalations(
    tier: Optional[int] = None,
    highway: Optional[str] = None,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Full escalation log."""
    query = """
        SELECT el.*, p.highway_id, p.km_marker
        FROM escalation_log el
        LEFT JOIN potholes p ON el.pothole_uuid = p.uuid
        WHERE 1=1
    """
    params = {}
    if tier:
        query += " AND el.tier_to = :tier"
        params["tier"] = tier
    if highway:
        query += " AND p.highway_id = :highway"
        params["highway"] = highway

    query += " ORDER BY el.escalated_at DESC LIMIT :limit"
    params["limit"] = limit

    result = await db.execute(text(query), params)
    return [dict(row._mapping) for row in result.fetchall()]
