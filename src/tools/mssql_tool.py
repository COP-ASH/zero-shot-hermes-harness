"""MSSQL tool — connects to the police database, fetches schema, runs read-only queries.

SECURITY: validates read-only SQL before execution.
MOCKING: If AGENT_MSSQL_DSN starts with "mock://", uses SQLite for unit testing.
"""
from __future__ import annotations

import re
from typing import Any

from src.config.settings import get_settings

_BLOCKED = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|EXEC|EXECUTE|TRUNCATE|REPLACE|MERGE)\b",
    re.IGNORECASE,
)

# Keep mock connection open in memory
_mock_conn = None


def _get_connection():
    settings = get_settings()
    dsn = settings.mssql_dsn

    if not dsn:
        raise ValueError("AGENT_MSSQL_DSN is not configured")

    if dsn.startswith("mock://"):
        import sqlite3
        global _mock_conn
        if _mock_conn is None:
            _mock_conn = sqlite3.connect(":memory:", check_same_thread=False)
            _mock_conn.row_factory = sqlite3.Row
            # Setup mock schema
            _mock_conn.execute("CREATE TABLE fir_data (district TEXT, crime_type TEXT, fir_count INTEGER, year INTEGER, month INTEGER)")
            _mock_conn.execute("INSERT INTO fir_data VALUES ('Lucknow', 'IPC 302', 45, 2024, 1)")
            _mock_conn.execute("INSERT INTO fir_data VALUES ('Agra', 'IPC 302', 32, 2024, 1)")
            _mock_conn.execute("INSERT INTO fir_data VALUES ('Kanpur', 'IPC 302', 28, 2024, 1)")
            _mock_conn.commit()
        return _mock_conn, True

    import pymssql
    # Parse DSN: Server=server;Database=db;User Id=user;Password=pwd;
    parts = dict(p.split('=', 1) for p in dsn.split(';') if '=' in p)
    
    # pymssql kwargs
    server = parts.get('Server', parts.get('SERVER', ''))
    database = parts.get('Database', parts.get('DATABASE', ''))
    user = parts.get('User Id', parts.get('UID', ''))
    password = parts.get('Password', parts.get('PWD', ''))

    conn = pymssql.connect(
        server=server,
        user=user,
        password=password,
        database=database,
        as_dict=True
    )
    return conn, False


def get_schema() -> dict[str, Any]:
    """Fetch available tables and columns."""
    conn, is_mock = _get_connection()
    schema = {}
    
    if is_mock:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cursor.fetchall()]
        for t in tables:
            cursor.execute(f"PRAGMA table_info({t})")
            columns = [{"name": r["name"], "dtype": r["type"]} for r in cursor.fetchall()]
            
            cursor.execute(f"SELECT COUNT(*) as c FROM {t}")
            row_count = cursor.fetchone()["c"]
            
            cursor.execute(f"SELECT * FROM {t} LIMIT 5")
            sample_rows = [dict(r) for r in cursor.fetchall()]
            
            schema[t] = {
                "view_name": t,
                "columns": columns,
                "row_count": row_count,
                "sample_rows": sample_rows
            }
        return schema
        
    try:
        with conn.cursor() as cursor:
            # Get tables
            cursor.execute("""
                SELECT TABLE_NAME 
                FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_TYPE = 'BASE TABLE' AND TABLE_CATALOG=DB_NAME()
            """)
            tables = [r["TABLE_NAME"] for r in cursor.fetchall()]

            for t in tables:
                cursor.execute(f"""
                    SELECT COLUMN_NAME, DATA_TYPE 
                    FROM INFORMATION_SCHEMA.COLUMNS 
                    WHERE TABLE_NAME = '{t}'
                """)
                columns = [{"name": r["COLUMN_NAME"], "dtype": r["DATA_TYPE"]} for r in cursor.fetchall()]
                
                cursor.execute(f"SELECT COUNT(*) as c FROM [{t}]")
                row_count = cursor.fetchone()["c"]
                
                cursor.execute(f"SELECT TOP 5 * FROM [{t}]")
                sample_rows = cursor.fetchall()
                
                schema[t] = {
                    "view_name": t,
                    "columns": columns,
                    "row_count": row_count,
                    "sample_rows": sample_rows
                }
    finally:
        conn.close()

    return schema


def run_sql(sql: str) -> dict[str, Any]:
    """Execute a read-only SQL query against MSSQL and return results."""
    sql = sql.strip()
    if _BLOCKED.search(sql):
        raise ValueError(
            "Security: only SELECT/WITH queries are allowed. "
            "Detected a write or DDL keyword in the query."
        )

    conn, is_mock = _get_connection()
    rows = []
    columns = []
    
    try:
        if is_mock:
            cursor = conn.cursor()
            cursor.execute(sql)
            rows = [dict(r) for r in cursor.fetchall()]
            if cursor.description:
                columns = [d[0] for d in cursor.description]
        else:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                rows = cursor.fetchall()
                if cursor.description:
                    columns = [d[0] for d in cursor.description]
    except Exception as exc:
        raise ValueError(f"MSSQL execution error: {exc}") from exc
    finally:
        if not is_mock:
            conn.close()

    if len(rows) > 10_000:
        rows = rows[:10_000]

    return {"columns": columns, "rows": rows, "row_count": len(rows)}
