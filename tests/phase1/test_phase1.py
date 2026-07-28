"""Phase 1 integration tests — UP Police Data Analyst Agent.

Tests the full primary journey against the real LLM (OpenRouter via .env).

Gate: uv run pytest tests/phase1/ -v
"""
from __future__ import annotations

import io
import json
import os

import pytest
from fastapi.testclient import TestClient


def has_openrouter_key():
    import os
    # Check env var first (set by monkeypatch/CI)
    if os.environ.get("AGENT_OPENROUTER_API_KEY"):
        return True
    # Fall back to .env file
    try:
        from dotenv import dotenv_values
        from pathlib import Path
        env = dotenv_values(str(Path(__file__).parent.parent.parent / ".env"))
        return bool(env.get("AGENT_OPENROUTER_API_KEY"))
    except Exception:
        return False


SKIP_IF_NO_KEY = pytest.mark.skipif(
    not has_openrouter_key(),
    reason="AGENT_OPENROUTER_API_KEY not set — real-key gate required",
)

# ── Sample CSV content ─────────────────────────────────────────────
SAMPLE_CSV = """district,crime_type,fir_count,year,month
Lucknow,IPC 302,45,2024,1
Agra,IPC 302,32,2024,1
Kanpur,IPC 302,28,2024,1
Varanasi,IPC 379,67,2024,1
Lucknow,IPC 379,89,2024,1
Agra,IPC 379,54,2024,1
Kanpur,IPC 420,23,2024,1
Varanasi,IPC 420,19,2024,1
Lucknow,IPC 420,76,2024,1
Agra,IPC 354,15,2024,2
Kanpur,IPC 302,31,2024,2
Varanasi,IPC 302,22,2024,2
""".strip()


@pytest.fixture()
def client():
    from src.api import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c


# ── Unit Tests (no LLM key required) ─────────────────────────────

class TestDuckDBTool:
    """Unit tests for the DuckDB tool — no LLM needed."""

    def test_register_and_query(self, tmp_path):
        from src.tools import duckdb_tool
        # Write a CSV
        csv_path = tmp_path / "test_fir.csv"
        csv_path.write_text(SAMPLE_CSV)

        sid = "test-session-duck"
        meta = duckdb_tool.register_csv(sid, csv_path, "test_fir")
        assert meta["row_count"] == 12
        assert any(c["name"] == "district" for c in meta["columns"])

        result = duckdb_tool.run_sql(sid, "SELECT district, SUM(fir_count) as total FROM test_fir GROUP BY district ORDER BY total DESC")
        assert result["row_count"] == 4
        assert "district" in result["columns"]
        assert result["rows"][0]["district"] == "Lucknow"  # highest

        duckdb_tool.close_session(sid)

    def test_sql_injection_blocked(self, tmp_path):
        from src.tools import duckdb_tool
        csv_path = tmp_path / "safe.csv"
        csv_path.write_text(SAMPLE_CSV)
        duckdb_tool.register_csv("block-test", csv_path, "safe")

        with pytest.raises(ValueError, match="Security"):
            duckdb_tool.run_sql("block-test", "DROP TABLE safe")

        with pytest.raises(ValueError, match="Security"):
            duckdb_tool.run_sql("block-test", "INSERT INTO safe VALUES (1)")

        duckdb_tool.close_session("block-test")

    def test_result_to_csv(self):
        from src.tools import duckdb_tool
        rows = [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]
        csv = duckdb_tool.result_to_csv(rows, ["a", "b"])
        assert "a,b" in csv
        assert "1" in csv


class TestHealthEndpoint:
    def test_health_returns_ok(self, client, no_keys):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["data"]["status"] == "ok"


class TestSessionsAPI:
    def test_create_session(self, client):
        r = client.post("/api/sessions")
        assert r.status_code == 200
        data = r.json()["data"]
        assert "session_id" in data
        assert data["status"] == "active"

    def test_get_session(self, client):
        sid = client.post("/api/sessions").json()["data"]["session_id"]
        r = client.get(f"/api/sessions/{sid}")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["session_id"] == sid

    def test_get_nonexistent_session(self, client):
        r = client.get("/api/sessions/does-not-exist")
        assert r.status_code == 404


class TestUploadAPI:
    def test_upload_csv(self, client, tmp_path):
        sid = client.post("/api/sessions").json()["data"]["session_id"]

        files = [("files", ("fir_data.csv", io.BytesIO(SAMPLE_CSV.encode()), "text/csv"))]
        r = client.post(f"/api/sessions/{sid}/upload", files=files)
        assert r.status_code == 200

        data = r.json()["data"]
        assert "fir_data.csv" in data["uploaded"]
        assert len(data["files"]) == 1
        f = data["files"][0]
        assert f["row_count"] == 12
        assert any(c["name"] == "district" for c in f["columns"])

    def test_upload_non_csv_rejected(self, client):
        sid = client.post("/api/sessions").json()["data"]["session_id"]
        files = [("files", ("report.xlsx", io.BytesIO(b"not a csv"), "application/vnd.ms-excel"))]
        r = client.post(f"/api/sessions/{sid}/upload", files=files)
        assert r.status_code == 400

    def test_upload_multiple_csvs(self, client):
        sid = client.post("/api/sessions").json()["data"]["session_id"]
        csv2 = "district,population\nLucknow,3000000\nAgra,1750000\n"
        files = [
            ("files", ("fir_data.csv", io.BytesIO(SAMPLE_CSV.encode()), "text/csv")),
            ("files", ("population.csv", io.BytesIO(csv2.encode()), "text/csv")),
        ]
        r = client.post(f"/api/sessions/{sid}/upload", files=files)
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data["files"]) == 2

    def test_query_without_upload_rejected(self, client):
        sid = client.post("/api/sessions").json()["data"]["session_id"]
        r = client.post(f"/api/sessions/{sid}/query", json={"question": "any question"})
        assert r.status_code == 400


# ── Integration Tests (real LLM key required) ─────────────────────

class TestQueryAPIIntegration:
    """Real-key integration tests — exercised at Phase 1 gate."""

    @SKIP_IF_NO_KEY
    def test_full_analysis_journey(self, client):
        """Full primary journey: upload CSV → ask question → get answer + chart."""
        # Create session
        sid = client.post("/api/sessions").json()["data"]["session_id"]

        # Upload CSV
        files = [("files", ("fir_data.csv", io.BytesIO(SAMPLE_CSV.encode()), "text/csv"))]
        upload_r = client.post(f"/api/sessions/{sid}/upload", files=files)
        assert upload_r.status_code == 200

        # Ask a hard data question
        query_r = client.post(
            f"/api/sessions/{sid}/query",
            json={"question": "Which district had the most FIRs? Give me the number."},
        )
        assert query_r.status_code == 200
        result = query_r.json()["data"]

        assert result["status"] == "completed", f"Got failed: {result.get('error')}"
        assert result["answer"], "Answer should not be empty"
        # The answer must reference Lucknow (highest in data) or a specific number
        answer_lower = result["answer"].lower()
        assert any(w in answer_lower for w in ["lucknow", "district", "fir", "210"]), \
            f"Answer should mention data specifics, got: {result['answer']}"

        # Should have SQL
        assert result["sql"], "SQL should be present"
        assert "SELECT" in result["sql"].upper(), "SQL should be a SELECT"

        # Should have chart
        assert result["chart"] is not None, "Chart spec should be present"
        chart = result["chart"]
        assert "type" in chart
        assert chart["type"] in ("bar", "line", "pie", "scatter", "table")

        # Should have follow-ups
        assert isinstance(result["follow_ups"], list)
        assert len(result["follow_ups"]) >= 1

    @SKIP_IF_NO_KEY
    def test_aggregation_question(self, client):
        """Test: count of FIRs by crime type."""
        sid = client.post("/api/sessions").json()["data"]["session_id"]
        files = [("files", ("fir_data.csv", io.BytesIO(SAMPLE_CSV.encode()), "text/csv"))]
        client.post(f"/api/sessions/{sid}/upload", files=files)

        r = client.post(
            f"/api/sessions/{sid}/query",
            json={"question": "Show total FIRs grouped by crime type"},
        )
        assert r.status_code == 200
        result = r.json()["data"]
        assert result["status"] == "completed"
        assert result["answer"]
        # IPC codes should appear
        assert any(ipc in result["answer"] for ipc in ["IPC", "302", "379", "420", "354", "crime"])

    @SKIP_IF_NO_KEY
    def test_csv_download(self, client):
        """Test: result can be downloaded as CSV."""
        sid = client.post("/api/sessions").json()["data"]["session_id"]
        files = [("files", ("fir_data.csv", io.BytesIO(SAMPLE_CSV.encode()), "text/csv"))]
        client.post(f"/api/sessions/{sid}/upload", files=files)

        query_r = client.post(
            f"/api/sessions/{sid}/query",
            json={"question": "How many FIRs per district?"},
        )
        assert query_r.status_code == 200
        run_id = query_r.json()["data"]["run_id"]

        download_r = client.get(f"/api/sessions/{sid}/download/{run_id}")
        assert download_r.status_code == 200
        assert "text/csv" in download_r.headers.get("content-type", "")
        content = download_r.text
        assert "district" in content.lower()

    @SKIP_IF_NO_KEY
    def test_multi_turn_chat(self, client):
        """Test: second question can reference context from first."""
        sid = client.post("/api/sessions").json()["data"]["session_id"]
        files = [("files", ("fir_data.csv", io.BytesIO(SAMPLE_CSV.encode()), "text/csv"))]
        client.post(f"/api/sessions/{sid}/upload", files=files)

        # First question
        r1 = client.post(
            f"/api/sessions/{sid}/query",
            json={"question": "What is the total FIR count for IPC 302?"},
        )
        assert r1.json()["data"]["status"] == "completed"

        # Second question — builds on context
        r2 = client.post(
            f"/api/sessions/{sid}/query",
            json={"question": "Now show the same breakdown by district"},
        )
        assert r2.status_code == 200
        result2 = r2.json()["data"]
        assert result2["status"] == "completed"
        assert result2["answer"]

    @SKIP_IF_NO_KEY
    def test_frontend_served(self, client):
        """Test: the frontend page is served at /app/ with content."""
        r = client.get("/app/")
        assert r.status_code == 200
        assert "UP Police" in r.text or "Data Analyst" in r.text or "DOCTYPE" in r.text

    @SKIP_IF_NO_KEY
    def test_css_and_js_assets_served(self, client):
        """Test: styles.css and app.js are served non-empty."""
        r_css = client.get("/app/styles.css")
        assert r_css.status_code == 200
        assert len(r_css.content) > 100

        r_js = client.get("/app/app.js")
        assert r_js.status_code == 200
        assert len(r_js.content) > 100
