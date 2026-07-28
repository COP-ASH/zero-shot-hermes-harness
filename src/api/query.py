"""Query API — POST /api/sessions/{session_id}/query

Runs the analysis graph on the analyst's question and returns the result.
Also handles chat history persistence and CSV download.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api._common import api_error, ok
from src.db.models import QueryRunRow, SessionRow
from src.db.session import get_session
from src.graph.runner import run_analysis

router = APIRouter(prefix="/api")


class QueryRequest(BaseModel):
    question: str


@router.post("/sessions/{session_id}/query")
def query_session(
    session_id: str,
    req: QueryRequest,
    sess: Session = Depends(get_session),
) -> dict:
    """Run a natural-language query against the session's uploaded CSVs."""
    session_row = sess.get(SessionRow, session_id)
    if session_row is None:
        raise api_error("not_found", f"Session {session_id} not found", 404)

    files_meta = json.loads(session_row.files_meta or "[]")
    if not files_meta:
        raise api_error("no_data", "Upload at least one CSV file before asking questions.", 400)

    # Build schema dict for the LLM
    schema = {
        m["view_name"]: {
            "columns": m["columns"],
            "row_count": m["row_count"],
            "sample_rows": m.get("sample_rows", []),
        }
        for m in files_meta
    }

    chat_history = json.loads(session_row.chat_history or "[]")

    # Run the analysis graph
    run_id = run_analysis(
        session_id=session_id,
        question=req.question,
        schema=schema,
        chat_history=chat_history,
    )

    # Fetch result
    qrun = sess.get(QueryRunRow, run_id)
    if qrun is None:
        raise api_error("run_not_found", f"Query run {run_id} vanished", 500)

    # Update chat history
    chat_history.append({"role": "user", "content": req.question})
    chat_history.append({
        "role": "assistant",
        "content": qrun.answer_text or "",
    })
    # Keep last 20 messages (10 Q&A pairs)
    if len(chat_history) > 20:
        chat_history = chat_history[-20:]
    session_row.chat_history = json.dumps(chat_history)

    follow_ups = []
    if qrun.follow_up_questions:
        try:
            follow_ups = json.loads(qrun.follow_up_questions)
        except Exception:
            follow_ups = []

    chart = None
    if qrun.chart_spec_json:
        try:
            chart = json.loads(qrun.chart_spec_json)
            # Enrich chart with actual data arrays for Plotly rendering
            if chart and qrun.result_csv:
                import io
                import pandas as pd
                df = pd.read_csv(io.StringIO(qrun.result_csv))
                x_col = chart.get("x")
                y_col = chart.get("y")
                if x_col and y_col and x_col in df.columns and y_col in df.columns:
                    # Limit to 50 data points for chart rendering
                    df_plot = df.head(50)
                    chart["x_data"] = df_plot[x_col].astype(str).tolist()
                    chart["y_data"] = pd.to_numeric(df_plot[y_col], errors="coerce").tolist()
                elif x_col and x_col in df.columns and len(df.columns) >= 2:
                    # Fallback: use first two columns
                    df_plot = df.head(50)
                    chart["x_data"] = df_plot.iloc[:, 0].astype(str).tolist()
                    chart["y_data"] = pd.to_numeric(df_plot.iloc[:, 1], errors="coerce").tolist()
        except Exception:
            chart = None


    return ok({
        "run_id": run_id,
        "status": qrun.status,
        "question": req.question,
        "answer": qrun.answer_text,
        "sql": qrun.planned_sql,
        "chart": chart,
        "follow_ups": follow_ups,
        "data_quality_notes": None,
        "error": qrun.error_message,
        "provider": qrun.provider,
        "model": qrun.model,
    })


@router.get("/sessions/{session_id}/download/{run_id}")
def download_result(
    session_id: str,
    run_id: str,
    sess: Session = Depends(get_session),
) -> Response:
    """Download the query result as a CSV file."""
    qrun = sess.get(QueryRunRow, run_id)
    if qrun is None or qrun.session_id != session_id:
        raise api_error("not_found", f"Run {run_id} not found in session {session_id}", 404)
    csv_content = qrun.result_csv or ""
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="result_{run_id[:8]}.csv"'},
    )
