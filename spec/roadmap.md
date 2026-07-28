# Roadmap — UP Police Data Analyst Agent

## What This Agent Does

The UP Police Data Analyst Agent is a browser-based AI assistant that lets crime analysts,
district officers, field investigators, and senior IPS officers ask natural-language questions
about police data. In Phase 1 analysts upload one or more CSVs (FIR logs, crime statistics,
officer records) and chat with the agent; it plans a DuckDB/pandas query, executes it,
reflects on the result, and returns an interactive chart + data table + plain-English answer
with the code it ran — all within one multi-turn session. Phase 2 extends the agent with a
read-only MSSQL connector protected by a DuckDB caching layer so the live production database
is barely touched.

## Who Uses It

Primary users are crime analysts at UP Police State HQ (daily deep-dive sessions) and
district-level data entry officers (occasional uploads, quick fact-checks). Senior IPS
officers consume weekly summary reports. Field investigators do on-demand lookups from desk
PCs during active cases. All users access the tool through a browser at
`http://localhost:8001/app/`.

## Core Problem Being Solved

Analysts currently export CSVs from multiple sources, open Excel, write manual pivot tables,
and produce static reports — a slow, error-prone process with no natural-language interface.
The agent replaces this with a conversational data-analysis loop: upload → ask → get
chart + answer in under 5 seconds. Phase 2 eliminates the export step entirely by querying
the centralised MSSQL database directly (through a caching layer).

## Success Criteria

- [ ] Analyst uploads a CSV, asks a question, and receives a correct natural-language answer
      with an interactive chart in under 5 seconds
- [ ] Agent shows step-by-step progress: "Planning…", "Executing…", "Reflecting…"
- [ ] Agent shows the DuckDB/Python code it used so the analyst can verify
- [ ] Agent proactively suggests 2–3 follow-up questions after each answer
- [ ] Agent flags data quality issues (nulls, duplicates, encoding) in uploaded CSVs
- [ ] Multi-CSV sessions: analyst can upload multiple files and ask cross-file questions

## What This Agent Does NOT Do (Out of Scope)

- Write to any database (read-only on all data sources)
- User authentication / role-based access control (Phase 1 is standalone, no auth)
- Real-time data streaming or live DB change notifications
- Send data outside the local machine (all processing on-premise)
- PDF report generation (deferred — labelled stub in Phase 1 UI)

## Key Constraints

- All data stays on-premise (no data to cloud LLMs; OpenRouter API calls carry only the
  question + schema description, never raw row data)
- Low latency: answers in under 5 seconds for typical CSV queries (10–100k rows)
- Low DB load on MSSQL: Phase 2 caches results in DuckDB; live DB is read-only reporting
- Large CSV support: chunked processing for files with millions of rows (DuckDB handles this)
- Prototype reliability bar: internal tool, stable enough for daily use, no audit trail required
- Port 8001, single-origin deployment

---

## Phases of Development

### Phase 1 — CSV Upload + Chat + Charts

- **Goal:** Analyst uploads one or more CSVs, asks a natural-language question, and receives
  a step-by-step answer with an interactive chart, data table, and the code used — all in one
  long multi-turn session within the browser.
- **Independent slices (parallel build units):**
  - `slice-a` (backend) — CSV upload endpoint, DuckDB ingestion, multi-step analysis graph
    (plan → execute → reflect → answer), session storage, `/api/sessions`, `/api/upload`,
    `/api/query` endpoints. Files: `src/`, `tests/`. Deps: none.
  - `slice-b` (frontend) — Police-branded chat UI with drag-and-drop CSV upload, schema
    panel, step-progress indicators, Plotly charts embedded in chat, code blocks, follow-up
    suggestions, download button, PDF report stub. Files: `frontend/public/`. Deps: none.
- **Key surfaces / files:**
  - Backend: `src/graph/state.py`, `src/graph/nodes.py`, `src/graph/edges.py`,
    `src/graph/agent.py`, `src/graph/runner.py`, `src/api/sessions.py`, `src/api/upload.py`,
    `src/api/query.py`, `src/api/health.py`, `src/db/models.py`, `src/tools/duckdb_tool.py`,
    `src/prompts/analyst_plan.md`, `src/prompts/analyst_execute.md`,
    `src/prompts/analyst_reflect.md`, `src/config/settings.py`, `pyproject.toml`
  - Frontend: `frontend/public/index.html`, `frontend/public/styles.css`,
    `frontend/public/app.js`
- **Gate command:** `uv run pytest tests/phase1/ -v`
- **How the user tests it:** Start the server with `uv run python -m src` (or use the
  background-launched URL below). Open `http://localhost:8001/app/`. Drag a CSV onto the
  upload area. See the schema panel populate. Type a question (e.g. "How many FIRs were
  filed per district in Q3?"). Watch the step indicators animate: Planning → Executing →
  Reflecting → Done. See a bar chart, data table, plain-English answer, and the Python code.
  Click "Download CSV" to get the result. See 2–3 follow-up suggestions. Labelled stubs:
  "Generate PDF Report" button (shows "Coming in Phase 2" tooltip), MSSQL tab (greyed out).

### Phase 2 — MSSQL Integration + Caching

- **Goal:** Wire the MSSQL connector so analysts can query the centralised police database
  without CSV uploads, with low latency (cached results) and minimal load on the live DB.
  Also wire the PDF report generator and session history persistence.
- **Independent slices (parallel build units):**
  - `slice-a` (backend) — MSSQL connector (read-only, pyodbc/pymssql), DuckDB caching layer
    (cache query results for configurable TTL), materialised schema metadata, `/api/mssql/query`
    endpoint, PDF report generator (reportlab or weasyprint). Files: `src/`, `tests/`. Deps: none.
  - `slice-b` (frontend) — Wire MSSQL tab to real endpoint; add TTL cache status badge; wire
    PDF download. Files: `frontend/public/`. Deps: none.
- **Key surfaces / files:**
  - Backend: `src/tools/mssql_tool.py`, `src/tools/cache_tool.py`, `src/api/mssql.py`,
    `src/api/reports.py`, `src/prompts/mssql_plan.md`, `src/db/models.py` (cache table),
    `pyproject.toml` (pymssql/pyodbc + reportlab)
  - Frontend: `frontend/public/app.js` (MSSQL tab), `frontend/public/index.html` (PDF btn)
- **Gate command:** `uv run pytest tests/phase2/ -v`
- **How the user tests it:** Open the app. Click the "MSSQL Database" tab. Enter connection
  details. Ask a question. See the cache-status badge ("Cached · 2m ago" or "Live"). Download
  a PDF report from the session.
