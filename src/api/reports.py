"""Reports API — GET /api/sessions/{session_id}/report.pdf"""
from __future__ import annotations

import json
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.api._common import api_error
from src.db.models import SessionRow, QueryRunRow
from src.db.session import get_session
from src.tools import pdf_tool

router = APIRouter(prefix="/api")

@router.get("/sessions/{session_id}/report.pdf")
def get_pdf_report(
    session_id: str,
    sess: Session = Depends(get_session)
) -> Response:
    """Generate a PDF report for the session."""
    session_row = sess.get(SessionRow, session_id)
    if session_row is None:
        raise api_error("not_found", f"Session {session_id} not found", 404)
        
    chat_history = json.loads(session_row.chat_history or "[]")
    
    # Fetch queries belonging to this session
    stmt = select(QueryRunRow).where(QueryRunRow.session_id == session_id).order_by(QueryRunRow.created_at)
    query_runs = sess.scalars(stmt).all()
    
    try:
        pdf_bytes = pdf_tool.generate_session_report(session_id, chat_history, list(query_runs))
    except Exception as exc:
        raise api_error("pdf_error", f"Failed to generate PDF: {exc}", 500)
        
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="report_{session_id[:8]}.pdf"'}
    )
