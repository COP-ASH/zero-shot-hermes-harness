"""AnalystState — the TypedDict flowing through the analysis graph."""
from __future__ import annotations

from typing import Any, TypedDict


class AnalystState(TypedDict, total=False):
    # Identity
    run_id: str
    session_id: str
    session_type: str  # "csv" or "mssql"

    # Input
    question: str
    schema: dict[str, Any]       # {view_name: {columns, row_count, sample_rows}}
    chat_history: list[dict]     # [{role, content}]
    retry_count: int

    # Intermediate
    planned_sql: str
    query_result_rows: list[dict]
    query_result_columns: list[str]
    reflection_ok: bool
    corrected_sql: str | None

    # Output
    answer_text: str
    chart_spec_json: str | None  # JSON string, Plotly spec
    follow_up_questions: list[str]
    data_quality_notes: str | None
    result_csv: str

    # Meta
    provider: str
    model: str
    status: str
    error: str | None
