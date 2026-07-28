"""Upload API — POST /api/sessions/{session_id}/upload

Accepts one or more CSV files, saves them to the upload directory,
registers them as DuckDB views, and returns schema metadata.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from src.api._common import api_error, ok
from src.config.settings import get_settings
from src.db.models import SessionRow
from src.db.session import get_session
from src.tools import duckdb_tool

router = APIRouter(prefix="/api")

_MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB per file


@router.post("/sessions/{session_id}/upload")
async def upload_csv(
    session_id: str,
    files: list[UploadFile] = File(...),
    sess: Session = Depends(get_session),
) -> dict:
    """Upload one or more CSV files into the session."""
    row = sess.get(SessionRow, session_id)
    if row is None:
        raise api_error("not_found", f"Session {session_id} not found", 404)

    settings = get_settings()
    upload_dir: Path = settings.get_upload_dir() / session_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    existing_meta = json.loads(row.files_meta or "[]")
    existing_views = {m["view_name"] for m in existing_meta}
    new_files_meta = []

    for upload_file in files:
        filename = upload_file.filename or "upload.csv"
        if not filename.lower().endswith(".csv"):
            raise api_error("invalid_file", f"{filename} is not a CSV file", 400)

        # Derive a clean view name from the file stem
        stem = Path(filename).stem
        view_name = "".join(c if c.isalnum() or c == "_" else "_" for c in stem).lower()
        if view_name[0].isdigit():
            view_name = "v_" + view_name

        # Handle duplicate view names
        if view_name in existing_views:
            i = 1
            while f"{view_name}_{i}" in existing_views:
                i += 1
            view_name = f"{view_name}_{i}"
        existing_views.add(view_name)

        file_path = upload_dir / filename
        content = await upload_file.read()
        file_path.write_bytes(content)

        try:
            meta = duckdb_tool.register_csv(session_id, file_path, view_name)
        except Exception as exc:
            raise api_error("csv_error", f"Failed to parse {filename}: {exc}", 400)

        new_files_meta.append({
            "name": filename,
            "view_name": view_name,
            "path": str(file_path),
            "columns": meta["columns"],
            "row_count": meta["row_count"],
            "sample_rows": meta["sample_rows"],
        })

    all_meta = existing_meta + new_files_meta
    row.files_meta = json.dumps(all_meta)

    return ok({
        "session_id": session_id,
        "uploaded": [m["name"] for m in new_files_meta],
        "files": all_meta,
    })
