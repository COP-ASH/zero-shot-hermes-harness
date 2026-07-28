"""Graph nodes — UP Police Data Analyst capability.

Implements the plan → execute → reflect → synthesize loop per spec/agent.md.

Node contract: (state) → partial state; failures go into state["error"]
so the error edge routes to handle_error — never raise through the graph.

ONE batched LLM call per node — never a call per output line/token.
"""
from __future__ import annotations

import json
import re

from src.graph.state import AnalystState
from src.llm.client import LLMClient, load_prompt
from src.llm.providers.base import LLMError
from src.tools import duckdb_tool
from src.observability.events import get_logger

_log = get_logger("nodes")


def _format_schema(schema: dict) -> str:
    """Format schema dict as a readable string for the LLM."""
    lines = []
    for view_name, meta in schema.items():
        cols = ", ".join(
            f"{c['name']} ({c['dtype']})" for c in meta.get("columns", [])
        )
        row_count = meta.get("row_count", "?")
        lines.append(f"View: {view_name}  ({row_count} rows)\n  Columns: {cols}")
    return "\n".join(lines)


def _format_chat_history(history: list[dict]) -> str:
    if not history:
        return "(no prior conversation)"
    last3 = history[-6:]  # last 3 Q&A pairs = 6 messages
    return "\n".join(f"{m['role'].upper()}: {m['content']}" for m in last3)


def _extract_json(text: str) -> dict:
    """Extract the first JSON object from LLM output (handles markdown fences)."""
    # Strip markdown code fences if present
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    # Find the first {...}
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON object found in LLM output: {text[:200]}")
    return json.loads(text[start:end])


def plan_query(state: AnalystState) -> AnalystState:
    """LLM writes a DuckDB SQL plan from the schema and question."""
    try:
        client = LLMClient()
        system = load_prompt("analyst_plan")

        retry_count = state.get("retry_count", 0)
        corrected_sql = state.get("corrected_sql")
        retry_context = ""
        if retry_count > 0 and corrected_sql:
            retry_context = f"Previous SQL failed or returned empty results. Try: {corrected_sql}"
        elif retry_count > 0:
            retry_context = "Previous SQL returned empty results — try a different approach."

        system_filled = (
            system
            .replace("{schema}", _format_schema(state.get("schema", {})))
            .replace("{chat_history}", _format_chat_history(state.get("chat_history", [])))
            .replace("{question}", state.get("question", ""))
            .replace("{retry_context}", retry_context)
        )
        sql = client.complete(system_filled, state.get("question", ""), max_tokens=512)
        # Strip markdown fences if present
        sql = re.sub(r"```(?:sql)?\s*", "", sql).strip().rstrip("`").strip()
        _log.info("plan_query", sql_preview=sql[:100])
        return {
            "planned_sql": sql,
            "corrected_sql": None,
            "provider": client.provider_name,
            "model": client.model,
            "error": None,
        }
    except LLMError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"plan_query failed: {exc}"}


def execute_query(state: AnalystState) -> AnalystState:
    """Execute the planned SQL via DuckDB tool — no LLM call."""
    sql = state.get("planned_sql", "")
    session_id = state.get("session_id", "")
    if not sql:
        return {"error": "No SQL to execute"}
    try:
        result = duckdb_tool.run_sql(session_id, sql)
        csv_str = duckdb_tool.result_to_csv(result["rows"], result["columns"])
        _log.info("execute_query", row_count=result["row_count"])
        return {
            "query_result_rows": result["rows"],
            "query_result_columns": result["columns"],
            "result_csv": csv_str,
            "error": None,
        }
    except ValueError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"execute_query failed: {exc}"}


def reflect(state: AnalystState) -> AnalystState:
    """LLM checks if the result is valid; retries with corrected SQL if not."""
    try:
        rows = state.get("query_result_rows", [])
        columns = state.get("query_result_columns", [])
        first_rows = rows[:3]

        client = LLMClient()
        system = load_prompt("analyst_reflect")
        system_filled = (
            system
            .replace("{question}", state.get("question", ""))
            .replace("{planned_sql}", state.get("planned_sql", ""))
            .replace("{columns}", str(columns))
            .replace("{row_count}", str(len(rows)))
            .replace("{first_rows}", json.dumps(first_rows, default=str))
        )

        raw = client.complete(system_filled, "Evaluate the result.", max_tokens=512)
        result = _extract_json(raw)
        ok = bool(result.get("ok", True))
        corrected_sql = result.get("corrected_sql")
        _log.info("reflect", ok=ok, retry_count=state.get("retry_count", 0))
        return {
            "reflection_ok": ok,
            "corrected_sql": corrected_sql if not ok else None,
            "error": None,
        }
    except LLMError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        # On reflect failure, be lenient — proceed to synthesize
        _log.warning("reflect_failed", error=str(exc))
        return {"reflection_ok": True, "corrected_sql": None, "error": None}


def synthesize(state: AnalystState) -> AnalystState:
    """LLM writes the final answer, chart spec, and follow-up questions."""
    try:
        rows = state.get("query_result_rows", [])
        columns = state.get("query_result_columns", [])
        rows_preview = rows[:20]

        client = LLMClient()
        system = load_prompt("analyst_synthesize")
        system_filled = (
            system
            .replace("{question}", state.get("question", ""))
            .replace("{planned_sql}", state.get("planned_sql", ""))
            .replace("{columns}", str(columns))
            .replace("{rows_preview}", json.dumps(rows_preview, default=str))
            .replace("{row_count}", str(len(rows)))
        )

        raw = client.complete(system_filled, "Synthesize the result.", max_tokens=1024)
        result = _extract_json(raw)

        chart = result.get("chart")
        chart_json = json.dumps(chart) if chart else None

        # Validate chart has required fields
        if chart and not isinstance(chart.get("type"), str):
            chart_json = None

        follow_ups = result.get("follow_ups", [])
        if not isinstance(follow_ups, list):
            follow_ups = []

        _log.info("synthesize", answer_len=len(result.get("answer", "")))
        return {
            "answer_text": result.get("answer", "Analysis complete."),
            "chart_spec_json": chart_json,
            "follow_up_questions": follow_ups[:3],
            "data_quality_notes": result.get("data_quality_notes"),
            "error": None,
        }
    except LLMError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"synthesize failed: {exc}"}


def handle_error(state: AnalystState) -> AnalystState:
    """Format errors gracefully for the user."""
    error = state.get("error", "An unknown error occurred.")
    user_msg = error
    if "401" in error or "403" in error:
        user_msg = "Authentication error — please check your API key in .env."
    elif "429" in error:
        user_msg = "Rate limit reached — please wait a moment and try again."
    elif "Security" in error:
        user_msg = "Query rejected: only read-only SELECT queries are allowed."
    elif "DuckDB" in error:
        user_msg = f"Query execution error: {error}"
    _log.error("handle_error", error=error)
    return {"answer_text": user_msg, "status": "failed"}


def finalize(state: AnalystState) -> AnalystState:
    return {"status": "completed"}
