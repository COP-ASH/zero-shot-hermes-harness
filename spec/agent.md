# Agent Design — UP Police Data Analyst

## Graph Framework

LangGraph `StateGraph` with a `TypedDict` state. Compiled once at import.

## Patterns Used

From `harness/patterns/agentic-ai.md`:

| Pattern | Applied How |
|---|---|
| #5 Tool Use | `duckdb_tool` executes generated SQL; `mssql_tool` (Phase 2) reads the live DB |
| #6 Planning | `plan_query` node: LLM produces an explicit SQL plan before executing |
| #4 Reflection | `reflect` node: LLM validates the query result; retries with corrected SQL (max 2) |
| #17 ReAct | Core loop: reason (plan) → act (execute) → observe (reflect) → answer |
| #22 LLM-Generated Code Execution | LLM writes DuckDB SQL; the tool executes it; result flows back |
| #12 Exception Handling | Every node catches errors into `state["error"]`; error edge → handle_error |
| #8 Memory | Session state carries schema + chat history within a session |
| #18 Guardrails | SQL validated for read-only (no INSERT/UPDATE/DELETE/DROP); output schema validated |

## Graph Nodes

```
plan_query
  IN:  {session_id, question, schema, chat_history, retry_count}
  OUT: {planned_sql, step_events: ["plan"]}
  LLM: ONE batched call with analyst_plan.md prompt
  — Writes DuckDB SQL targeting the registered view names
  — Never loops per line; generates the full SQL in one call

execute_query
  IN:  {planned_sql, session_id}
  OUT: {query_result_rows, query_result_columns, step_events: ["execute"]}
  TOOL: duckdb_tool.run_sql(session_id, sql)
  — No LLM call; pure tool execution
  — On tool error: sets state["error"] → error edge

reflect
  IN:  {query_result_rows, planned_sql, question, retry_count}
  OUT: {reflection_ok: bool, corrected_sql?, step_events: ["reflect"]}
  LLM: ONE batched call with analyst_reflect.md prompt
  — Checks: result non-empty? column names sensible? answerable?
  — If not OK and retry_count < 2: sets corrected_sql, increments retry_count → loop back to plan_query
  — If not OK after 2 retries: sets state["error"] → error edge

synthesize
  IN:  {query_result_rows, query_result_columns, question, chat_history, planned_sql}
  OUT: {answer_text, chart_spec_json, follow_up_questions, step_events: ["synthesize"]}
  LLM: ONE batched call with analyst_reflect.md → synthesize section
  — answer_text: plain English
  — chart_spec_json: Plotly JSON (type, x, y, title)
  — follow_up_questions: list of 3 strings

handle_error
  IN:  {error}
  OUT: {status: "failed", answer_text: user-friendly error message}

finalize
  IN:  {answer_text, chart_spec_json, follow_up_questions, provider, model}
  OUT: {status: "completed"}
  — Writes result to session row in SQLite
```

## Graph Edges

```
START → plan_query
plan_query → execute_query
execute_query → [error? → handle_error | ok → reflect]
reflect → [retry? → plan_query | error? → handle_error | ok → synthesize]
synthesize → finalize
finalize → END
handle_error → END
```

## State TypedDict (AnalystState)

```python
class AnalystState(TypedDict, total=False):
    # Identity
    run_id: str
    session_id: str

    # Input
    question: str
    schema: dict          # {table_name: [{col, dtype, sample}]}
    chat_history: list    # [{role, content}]
    retry_count: int

    # Intermediate
    planned_sql: str
    query_result_rows: list[dict]
    query_result_columns: list[str]
    reflection_ok: bool
    corrected_sql: str | None

    # Output
    answer_text: str
    chart_spec_json: str   # JSON string, Plotly spec
    follow_up_questions: list[str]
    step_events: list[str]

    # Meta
    provider: str
    model: str
    status: str
    error: str | None
```

## SSE Step Events

Each node emits an SSE event before starting its work:
```json
{"step": "plan",      "status": "running", "payload": null}
{"step": "execute",   "status": "running", "payload": {"sql": "SELECT ..."}}
{"step": "reflect",   "status": "running", "payload": null}
{"step": "synthesize","status": "running", "payload": null}
{"step": "done",      "status": "completed", "payload": {
  "answer": "...", "chart": {...}, "code": "...", "follow_ups": [...]
}}
```

## Retry Logic

- `reflect` node returns `reflection_ok=False` + `corrected_sql` when result is empty or
  clearly wrong
- The `after_reflect` edge sends back to `plan_query` (with `corrected_sql` replacing
  `planned_sql`) if `retry_count < 2`
- After 2 retries, the error edge fires → `handle_error`

## Guardrails

- `execute_query` validates the SQL string: rejects any statement containing `INSERT`,
  `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `EXEC` (case-insensitive) before passing
  to DuckDB — returns error state immediately
- `synthesize` output validated: `chart_spec_json` must parse as valid JSON with `type` key
