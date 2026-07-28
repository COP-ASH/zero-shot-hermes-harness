"""Sessions API — POST /api/sessions (create), GET /api/sessions/{id} (fetch)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.api._common import api_error, ok
from src.db.models import SessionRow
from src.db.session import get_session

router = APIRouter(prefix="/api")


@router.post("/sessions")
def create_session(sess: Session = Depends(get_session)) -> dict:
    """Create a new analyst session."""
    row = SessionRow(files_meta=json.dumps([]), chat_history=json.dumps([]))
    sess.add(row)
    sess.flush()
    sess.refresh(row)
    return ok({"session_id": row.id, "status": row.status})


@router.get("/sessions/{session_id}")
def get_session_info(session_id: str, sess: Session = Depends(get_session)) -> dict:
    row = sess.get(SessionRow, session_id)
    if row is None:
        raise api_error("not_found", f"Session {session_id} not found", 404)
    files_meta = json.loads(row.files_meta or "[]")
    chat_history = json.loads(row.chat_history or "[]")
    return ok({
        "session_id": row.id,
        "status": row.status,
        "files": files_meta,
        "chat_history": chat_history,
    })
