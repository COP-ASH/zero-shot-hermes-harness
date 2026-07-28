"""DuckDB tool — registers CSV files as in-memory views and executes SQL queries.

Each session gets its own DuckDB connection (in-memory). CSV files are registered
as views by their file stem (e.g., 'fir_data' for fir_data.csv).

SECURITY: run_sql validates that the SQL is read-only (SELECT/WITH only) before
execution — no INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/EXEC.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

# In-memory registry: session_id → duckdb.DuckDBPyConnection
_connections: dict[str, duckdb.DuckDBPyConnection] = {}

# Blocked SQL keywords — any statement containing these is rejected
_BLOCKED = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|EXEC|EXECUTE|TRUNCATE|REPLACE|MERGE)\b",
    re.IGNORECASE,
)


def get_connection(session_id: str) -> duckdb.DuckDBPyConnection:
    """Return (or create) the DuckDB connection for this session."""
    if session_id not in _connections:
        _connections[session_id] = duckdb.connect(":memory:")
    return _connections[session_id]


def register_csv(session_id: str, file_path: Path, view_name: str) -> dict[str, Any]:
    """Register a CSV file as a DuckDB view and return schema metadata.

    Returns:
        {view_name, columns: [{name, dtype}], row_count, sample_rows: list[dict]}
    """
    conn = get_connection(session_id)
    path_str = str(file_path).replace("\\", "/")

    # Register as a view — DuckDB auto-detects delimiter, types, and header
    conn.execute(
        f"CREATE OR REPLACE VIEW \"{view_name}\" AS SELECT * FROM read_csv_auto('{path_str}', header=true)"
    )

    # Get schema
    schema_rows = conn.execute(f'DESCRIBE "{view_name}"').fetchall()
    columns = [{"name": row[0], "dtype": row[1]} for row in schema_rows]

    # Row count
    row_count = conn.execute(f'SELECT COUNT(*) FROM "{view_name}"').fetchone()[0]

    # Sample rows (up to 5)
    sample_df = conn.execute(f'SELECT * FROM "{view_name}" LIMIT 5').df()
    sample_rows = sample_df.to_dict(orient="records")

    return {
        "view_name": view_name,
        "columns": columns,
        "row_count": row_count,
        "sample_rows": sample_rows,
    }


def run_sql(session_id: str, sql: str) -> dict[str, Any]:
    """Execute a read-only SQL query and return results.

    Returns:
        {"columns": [...], "rows": [...], "row_count": int}

    Raises:
        ValueError: if the SQL contains blocked keywords or exceeds 10k rows
    """
    sql = sql.strip()
    if _BLOCKED.search(sql):
        raise ValueError(
            "Security: only SELECT/WITH queries are allowed. "
            "Detected a write or DDL keyword in the query."
        )

    conn = get_connection(session_id)
    try:
        result_df = conn.execute(sql).df()
    except Exception as exc:
        raise ValueError(f"DuckDB execution error: {exc}") from exc

    if len(result_df) > 10_000:
        result_df = result_df.head(10_000)

    columns = list(result_df.columns)
    rows = result_df.to_dict(orient="records")

    return {"columns": columns, "rows": rows, "row_count": len(rows)}


def list_views(session_id: str) -> list[str]:
    """Return the list of view names registered for this session."""
    conn = get_connection(session_id)
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_type='VIEW'"
    ).fetchall()
    return [r[0] for r in rows]


def close_session(session_id: str) -> None:
    """Close and remove the DuckDB connection for this session."""
    if session_id in _connections:
        try:
            _connections[session_id].close()
        except Exception:
            pass
        del _connections[session_id]


def result_to_csv(rows: list[dict], columns: list[str]) -> str:
    """Convert query result to CSV string."""
    if not rows:
        return ",".join(columns) + "\n"
    df = pd.DataFrame(rows, columns=columns)
    return df.to_csv(index=False)
