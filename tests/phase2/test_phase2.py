"""Integration and unit tests for Phase 2 MSSQL features."""

import os
import pytest
from fastapi.testclient import TestClient

from src.tools import cache_tool

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AGENT_MSSQL_DSN", "mock://sqlite")
    # Clear cache before each test
    try:
        cache_tool.clear_cache()
    except Exception:
        pass
        
    from src.api import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c


def has_openrouter_key():
    if os.environ.get("AGENT_OPENROUTER_API_KEY"):
        return True
    try:
        from dotenv import dotenv_values
        from pathlib import Path
        env = dotenv_values(str(Path(__file__).parent.parent.parent / ".env"))
        return bool(env.get("AGENT_OPENROUTER_API_KEY"))
    except Exception:
        return False

SKIP_IF_NO_KEY = pytest.mark.skipif(
    not has_openrouter_key(),
    reason="AGENT_OPENROUTER_API_KEY not found in env or .env file",
)


class TestMSSQLAPI:
    def test_connect_mssql(self, client):
        r = client.post("/api/mssql/connect")
        assert r.status_code == 200
        data = r.json()["data"]
        assert "session_id" in data
        assert len(data["files"]) > 0
        
        # In our mock, there is a "fir_data" table
        fir_table = next((f for f in data["files"] if f["view_name"] == "fir_data"), None)
        assert fir_table is not None
        assert fir_table["row_count"] == 3

    @SKIP_IF_NO_KEY
    def test_mssql_query(self, client):
        # 1. Connect
        r = client.post("/api/mssql/connect")
        assert r.status_code == 200
        sid = r.json()["data"]["session_id"]
        
        # 2. Query
        r = client.post(f"/api/mssql/query/{sid}", json={"question": "What is the total fir_count in Lucknow?"})
        assert r.status_code == 200
        data = r.json()["data"]
        assert "answer" in data
        assert "45" in data["answer"]  # Lucknow has 45 IPC 302 cases in our mock
        assert data["error"] is None
        
        # 3. Test caching behavior
        # Run identical query again
        r2 = client.post(f"/api/mssql/query/{sid}", json={"question": "What is the total fir_count in Lucknow?"})
        data2 = r2.json()["data"]
        
        # The logs would show "cached=True" but we can't easily assert that here without reading logs.
        # Instead, we just ensure it returns correctly and doesn't fail.
        assert "45" in data2["answer"]

    def test_pdf_generation(self, client):
        # 1. Connect
        r = client.post("/api/mssql/connect")
        sid = r.json()["data"]["session_id"]
        
        # 2. PDF without queries should return empty report
        r = client.get(f"/api/sessions/{sid}/report.pdf")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert len(r.content) > 1000  # Basic PDF structure
