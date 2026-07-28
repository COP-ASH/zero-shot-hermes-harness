# NOTES.md — Hermes Build Journal

## Run: UP Police Data Analyst Agent — 2026-07-28 22:38 IST

### Entry 1: Session start + intake

- `clarify` tool worked for all 5 product rounds + technical round with no failures
- User selected OpenRouter with `anthropic/claude-sonnet-4-6` — good choice for complex SQL generation
- `.env` was missing (only `.env.example` existed) — created via `Copy-Item` then wrote key via PowerShell replace

### Entry 2: API key verification

- Used `uv run python -c "..."` because `python` resolves to the wrong interpreter without the venv
- The path to `.env` in `dotenv_values()` must be ABSOLUTE from a known anchor — `Path(__file__).parent.parent...` in test files, resolved repo root for the verify script
- Live API call confirmed key valid before starting build

### Entry 3: Settings duplication bug

- Used `replace_file_content` to update `settings.py` but the replacement content included a second full `Settings` class — caused by wrapping the new code between the original partial target
- **Lesson:** When replacing a partial match at the top of a file, the tool appends new content + keeps the rest of the original. Overwrite the full file with `write_to_file(Overwrite=True)` for complete rewrites

### Entry 4: DuckDB tool design

- DuckDB sessions stored in a module-level dict (`_connections`) keyed by session_id
- `register_csv` uses `read_csv_auto()` with `header=true` — works for all standard CSV formats
- SQL injection guard uses `re.IGNORECASE` regex on blocked keywords before every execute — no performance hit at this scale

### Entry 5: Test skip condition failure

- `has_openrouter_key()` used `Path(__file__).parent.parent` — wrong path from `tests/phase1/` (needed `.parent.parent.parent` to reach repo root)
- Integration tests skipped on first run despite key being present
- **Lesson:** Always verify the path anchor for `.env` loading in test files — count parent dirs carefully from the test file location

### Entry 6: Chart data enrichment

- LLM synthesize prompt returns column names (`x: "district"`, `y: "fir_count"`) not data arrays
- Added chart enrichment in `query.py` that reads `result_csv` and maps column names → actual data arrays
- `pandas.to_numeric(errors="coerce")` handles mixed-type columns gracefully

### Harness Improvements to Propose

1. **`test_path` helper**: A `get_repo_root()` function in `tests/conftest.py` to avoid per-file path counting
2. **Settings rewrite note**: `replace_file_content` is not safe for whole-file rewrites with overlapping targets — doc should recommend `write_to_file(Overwrite=True)` for complete replacements
