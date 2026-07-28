# Architecture — UP Police Data Analyst Agent

## Overview

A single-origin FastAPI + LangGraph Python application. The analyst interacts through a
zero-build static browser UI. The backend hosts a multi-step analysis graph powered by
DuckDB (in-process columnar engine) for fast, local query execution over uploaded CSVs.
In Phase 2, an MSSQL connector (read-only) is added behind a DuckDB caching layer.

---

## Stack

| Layer | Choice | Notes |
|---|---|---|
| Language | Python 3.11 | baseline |
| Web framework | FastAPI 0.115+ | baseline |
| Graph framework | LangGraph 0.2+ | baseline; extended with analysis nodes |
| LLM provider | OpenRouter (anthropic/claude-sonnet-4-6) | via `AGENT_OPENROUTER_API_KEY` |
| CSV query engine | DuckDB (in-process) | fast columnar SQL over uploaded files; no server needed |
| Session store | SQLite (via SQLAlchemy 2.0) | baseline; stores sessions, uploads metadata, query history |
| MSSQL connector | pymssql (Phase 2) | read-only; protected by DuckDB cache layer |
| DuckDB cache | DuckDB persistent file (Phase 2) | materialises frequent MSSQL query results; TTL-based |
| Frontend | Zero-build static (HTML/CSS/JS) | served at `/app` by FastAPI; Plotly.js for charts |
| Port | 8001 | default; overridable via `PORT` env var |
| Data residency | 100% on-premise | only question + schema metadata leave the machine (to OpenRouter) |

---

## Component Map

```
Browser (http://localhost:8001/app/)
  ├── Drag-drop CSV upload → POST /api/upload
  ├── Schema panel (columns, types, row count)
  ├── Chat pane → POST /api/query (streaming step events via SSE)
  ├── Chart area (Plotly.js, embedded in chat bubbles)
  ├── Code block (generated DuckDB SQL / pandas code)
  ├── Download CSV button → GET /api/sessions/{id}/download
  └── [STUB] MSSQL tab / PDF report button

FastAPI app (src/)
  ├── POST /api/sessions          — create a new analysis session
  ├── POST /api/upload            — ingest CSV(s) into DuckDB; return schema
  ├── POST /api/query             — run analysis graph; return SSE stream of steps + result
  ├── GET  /api/sessions/{id}/download — return result as CSV
  ├── GET  /health                — provider presence check
  └── GET  /app/*                 — static frontend

LangGraph analysis graph (src/graph/)
  ├── plan_query     — LLM writes a DuckDB SQL plan
  ├── execute_query  — runs the SQL via DuckDB tool
  ├── reflect        — LLM checks result validity; retries if empty/error (max 2 retries)
  ├── synthesize     — LLM writes the final answer + chart spec + follow-up questions
  ├── handle_error   — formats errors gracefully
  └── finalize       — writes result to session row

DuckDB tool (src/tools/duckdb_tool.py)
  — registers uploaded CSV files as DuckDB views per session
  — executes SQL strings; returns columnar results as dicts
  — used both for CSV queries (Phase 1) and as the cache layer (Phase 2)
```

---

## Data Flow (Phase 1)

```
1. Analyst drags CSV → POST /api/upload
2. Backend: pandas reads header + 5 sample rows for schema; DuckDB registers file as a view
3. Session row created (SQLite); schema returned to UI
4. Analyst types question → POST /api/query
5. Graph invoked with {session_id, question, schema}:
   a. plan_query: LLM generates DuckDB SQL (one batched call)
   b. execute_query: DuckDB tool runs SQL; returns rows
   c. reflect: LLM checks result (non-empty? sensible?); if not → retry with corrected SQL (max 2)
   d. synthesize: LLM writes answer + Plotly chart JSON + 3 follow-up questions (one batched call)
6. Each step emits an SSE event: {step, status, payload}
7. Frontend renders step indicators, then chart + answer + code block
8. Result written to session row; GET /sessions/{id}/download serves CSV
```

---

## Security / Privacy

- Only the question text + table schema (column names + types) are sent to the LLM.
  **Raw row data never leaves the server.**
- DuckDB runs in-process; uploaded CSV files live in a temp directory, cleaned up on session end.
- MSSQL connector (Phase 2) uses a read-only service account; no writes, no DDL.

---

## Environment Variables

| Variable | Purpose |
|---|---|
| `AGENT_OPENROUTER_API_KEY` | OpenRouter API key (required) |
| `AGENT_LLM_MODEL` | Model slug (default: `anthropic/claude-sonnet-4-6`) |
| `AGENT_DATABASE_URL` | SQLite path for session store (default: `sqlite:///./data/app.db`) |
| `PORT` | HTTP port (default: 8001) |
| `AGENT_LOG_LEVEL` | Logging level (default: INFO) |
| `AGENT_UPLOAD_DIR` | Directory for uploaded CSVs (default: `./data/uploads`) |
| `AGENT_MSSQL_DSN` | MSSQL connection string — Phase 2 only |
| `AGENT_CACHE_TTL_SECONDS` | DuckDB cache TTL for MSSQL results — Phase 2, default 300 |
