"""Cache tool — DuckDB caching layer for MSSQL queries.

Protects the live MSSQL database by caching results for a configurable TTL.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import duckdb

from src.config.settings import get_settings
from src.tools import mssql_tool

_cache_conn: duckdb.DuckDBPyConnection | None = None

def _get_cache_conn() -> duckdb.DuckDBPyConnection:
    global _cache_conn
    if _cache_conn is None:
        _cache_conn = duckdb.connect("./data/mssql_cache.duckdb")
        # Create cache table if not exists
        _cache_conn.execute("""
            CREATE TABLE IF NOT EXISTS mssql_cache (
                query_hash VARCHAR PRIMARY KEY,
                columns_json VARCHAR,
                rows_json VARCHAR,
                row_count INTEGER,
                created_at TIMESTAMP
            )
        """)
    return _cache_conn

def _hash_query(sql: str) -> str:
    return hashlib.sha256(sql.strip().encode()).hexdigest()

def run_mssql_query(sql: str) -> dict:
    """Run MSSQL query, utilizing DuckDB cache if valid."""
    settings = get_settings()
    ttl_seconds = settings.cache_ttl_seconds
    
    conn = _get_cache_conn()
    qhash = _hash_query(sql)
    
    # Check cache
    cached = conn.execute(
        "SELECT columns_json, rows_json, row_count, created_at FROM mssql_cache WHERE query_hash = ?",
        [qhash]
    ).fetchone()
    
    if cached:
        created_at = cached[3]
        now = datetime.now(timezone.utc).replace(tzinfo=None) # duckdb returns naive datetime
        if (now - created_at).total_seconds() <= ttl_seconds:
            # Cache hit
            return {
                "columns": json.loads(cached[0]),
                "rows": json.loads(cached[1]),
                "row_count": cached[2],
                "cached": True
            }
            
    # Cache miss or expired — fetch from live MSSQL
    result = mssql_tool.run_sql(sql)
    
    # Update cache
    cols_json = json.dumps(result["columns"])
    rows_json = json.dumps(result["rows"], default=str)
    
    conn.execute(
        """
        INSERT INTO mssql_cache (query_hash, columns_json, rows_json, row_count, created_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT (query_hash) DO UPDATE SET 
            columns_json=EXCLUDED.columns_json,
            rows_json=EXCLUDED.rows_json,
            row_count=EXCLUDED.row_count,
            created_at=EXCLUDED.created_at
        """,
        [qhash, cols_json, rows_json, result["row_count"]]
    )
    
    result["cached"] = False
    return result

def clear_cache():
    """Clear all cached queries."""
    conn = _get_cache_conn()
    conn.execute("DELETE FROM mssql_cache")
