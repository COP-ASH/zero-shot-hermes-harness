# UP Police Data Analyst Agent

> All commands run from the **repo root** (`c:\Users\Ashwani Gupta\agent\zero-shot-hermes-harness`).

An AI-powered data analyst for UP (Uttar Pradesh) Police. Upload CSV files (FIR records, crime statistics, officer logs) and ask natural-language questions — get interactive charts, data tables, plain-English answers, and the SQL/Python code used to produce them.

## Quick Start

### 1. Set up environment

```
# repo root
copy .env.example .env
# Edit .env — set AGENT_OPENROUTER_API_KEY=sk-or-v1-...
```

### 2. Install dependencies

```
# repo root
uv sync
```

### 3. Run the app

```
# repo root
uv run python -m src
```

Open **http://localhost:8001/app/** in your browser.

### 4. Use the agent

1. Drag and drop a CSV file (FIR records, crime data, etc.) onto the upload area
2. See the schema panel populate automatically (column names, types, row count)
3. Type a question: *"Which district had the most IPC 302 cases?"*
4. Watch the step indicators: Planning → Executing → Reflecting → Done
5. Get a bar chart + plain-English answer + the DuckDB SQL used
6. Click **Download CSV** to get the result data
7. Click follow-up suggestions to dig deeper

## Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `AGENT_OPENROUTER_API_KEY` | OpenRouter API key (**required**) | — |
| `AGENT_LLM_MODEL` | LLM model slug | `anthropic/claude-sonnet-4-6` |
| `AGENT_DATABASE_URL` | SQLite path for session store | `sqlite:///./data/app.db` |
| `AGENT_UPLOAD_DIR` | Directory for uploaded CSVs | `./data/uploads` |
| `PORT` | HTTP port | `8001` |
| `AGENT_LOG_LEVEL` | Logging level | `INFO` |

## Running Tests

```
# repo root
uv run pytest tests/phase1/ -v
```

- **Unit tests** (no LLM key needed): DuckDB tool, session/upload API, health check
- **Integration tests** (real LLM key from `.env`): full journey, aggregation, download, multi-turn chat, frontend serving

## Architecture

```
Browser → FastAPI → LangGraph analysis graph → DuckDB (in-process)
                                              → OpenRouter LLM
                                              → SQLite (session store)
```

**Analysis graph nodes:**
1. `plan_query` — LLM writes DuckDB SQL from schema + question
2. `execute_query` — DuckDB runs the SQL (read-only, validated)
3. `reflect` — LLM checks if result is valid; retries up to 2x with corrected SQL
4. `synthesize` — LLM writes answer + Plotly chart spec + 3 follow-up questions

**Privacy:** Only the question text + table schema (column names + types) are sent to the LLM. **Raw row data never leaves the server.**

## What's in Phase 2

- 🗄️ **MSSQL connector** — read-only, protected by a DuckDB caching layer (TTL-based)
- 📄 **PDF report generator** — export session as a formatted report
- 🔄 **Materialized views** — pre-computed views for frequent MSSQL queries

## File Layout

```
src/
  api/          — FastAPI routes (sessions, upload, query, health)
  config/       — Settings (env prefix AGENT_)
  db/           — SQLAlchemy models (sessions, query_runs)
  graph/        — LangGraph nodes, edges, state, agent, runner
  llm/          — LLM client + OpenRouter provider
  tools/        — DuckDB tool (register CSV views, execute SQL)
  prompts/      — Analyst prompts (plan, synthesize, reflect)
frontend/public/ — Zero-build static UI (HTML/CSS/JS + Plotly)
tests/phase1/   — Unit + integration tests
```
