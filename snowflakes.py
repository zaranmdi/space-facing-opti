from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import snowflake.connector
from dotenv import load_dotenv

# Load .env from repo root first, then allow local cwd override if present.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
load_dotenv()


def snowflake_connect():
    params = {
        "user": "267714",
        "account": "bunnings.australia-east.privatelink",
        "role": "SPACE_PRODUCTIVITY_ANALYST_DE_GENERAL_PRD",
        "warehouse": "PRD_DEVELOPER_WH",
        "authenticator": "externalbrowser",
    }

    conn = snowflake.connector.connect(**params)
    conn.cursor().execute("SELECT CURRENT_USER()")
    print("Connection OK")
    return conn


def fetch_dataframe(conn, sql: str) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetch_pandas_all()


def apply_store_filter(
    base_sql: str, id_col: str, store_codes: list[str] | str | None
) -> str:
    if store_codes in (None, "all"):
        return base_sql
    if isinstance(store_codes, str):
        raise TypeError('store_filter must be "all" or a list such as ["6402", "9476"]')

    codes = [str(code).strip() for code in store_codes if str(code).strip()]
    if not codes:
        return base_sql

    codes_literal = ", ".join(
        "'" + code.replace("'", "''") + "'" for code in sorted(set(codes))
    )
    clean_sql = base_sql.rstrip().rstrip(";").rstrip()
    return f"SELECT * FROM (\n{clean_sql}\n) _filtered\nWHERE {id_col} IN ({codes_literal})"


def load_filtered_sql(
    paths: dict[str, Path],
    sql_file: str,
    id_col: str,
    store_filter: list[str] | str | None,
) -> str:
    base_sql = (paths["sql_dir"] / sql_file).read_text(encoding="utf-8")
    return apply_store_filter(base_sql, id_col, store_filter)