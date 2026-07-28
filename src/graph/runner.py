"""run_analysis() — entry point the query API calls.

Creates the query_run row, invokes the analysis graph, persists the outcome.
Errors land in the row (status=failed + message), never as a crash.
"""
from __future__ import annotations

import json

from src.db.models import QueryRunRow
from src.db.session import create_db_session
from src.graph.agent import agentic_ai
from src.graph.state import AnalystState
from src.observability.events import get_logger, log_span


def run_analysis(
    session_id: str,
    question: str,
    schema: dict,
    chat_history: list[dict],
) -> str:
    """Run the analysis graph and return the query_run_id."""
    log = get_logger("runner")

    with create_db_session() as session:
        qrun = QueryRunRow(
            session_id=session_id,
            question=question,
            status="running",
        )
        session.add(qrun)
        session.flush()
        run_id = qrun.id

    initial: AnalystState = {
        "run_id": run_id,
        "session_id": session_id,
        "question": question,
        "schema": schema,
        "chat_history": chat_history,
        "retry_count": 0,
        "error": None,
    }

    with log_span(log, "analysis_run", run_id=run_id, session_id=session_id) as span:
        final: AnalystState = agentic_ai.invoke(initial)
        span["status"] = final.get("status", "completed")

    with create_db_session() as session:
        qrun = session.get(QueryRunRow, run_id)
        if qrun is not None:
            qrun.status = final.get("status", "completed")
            qrun.planned_sql = final.get("planned_sql")
            qrun.answer_text = final.get("answer_text")
            qrun.chart_spec_json = final.get("chart_spec_json")
            qrun.result_csv = final.get("result_csv")
            follow_ups = final.get("follow_up_questions", [])
            qrun.follow_up_questions = json.dumps(follow_ups) if follow_ups else None
            qrun.provider = final.get("provider")
            qrun.model = final.get("model")
            qrun.error_message = final.get("error")

    return run_id
