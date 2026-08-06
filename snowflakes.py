from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import snowflake.connector
from dotenv import load_dotenv

try:
    import streamlit as st
except Exception:  # pragma: no cover - Streamlit is optional for non-app usage.
    st = None

# Load .env from repo root first, then allow local cwd override if present.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
load_dotenv()


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    cleaned = value.strip()
    return cleaned or default


def _secret(name: str) -> str | None:
    if st is None:
        return None
    try:
        value = st.secrets.get(name)
    except Exception:
        return None
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _setting(name: str, default: str | None = None) -> str | None:
    secret_value = _secret(name)
    if secret_value is not None:
        return secret_value
    return _env(name, default)


def build_snowflake_params() -> dict[str, str]:
    connection_name = _setting("SNOWFLAKE_CONNECTION_NAME")
    if connection_name:
        params = {"connection_name": connection_name}
    else:
        params = {
            "user": _setting("SNOWFLAKE_USER", "267714"),
            "account": _setting("SNOWFLAKE_ACCOUNT", "bunnings.australia-east.privatelink"),
            "role": _setting("SNOWFLAKE_ROLE", "SPACE_PRODUCTIVITY_ANALYST_DE_GENERAL_PRD"),
            "warehouse": _setting("SNOWFLAKE_WAREHOUSE", "PRD_DEVELOPER_WH"),
        }

    optional_settings = {
        "database": _setting("SNOWFLAKE_DATABASE"),
        "schema": _setting("SNOWFLAKE_SCHEMA"),
        "password": _setting("SNOWFLAKE_PASSWORD"),
        "authenticator": _setting("SNOWFLAKE_AUTHENTICATOR"),
        "token": _setting("SNOWFLAKE_TOKEN"),
    }

    if optional_settings["token"] and not optional_settings["authenticator"]:
        optional_settings["authenticator"] = "oauth"

    if (
        not optional_settings["authenticator"]
        and not optional_settings["password"]
        and not optional_settings["token"]
        and "connection_name" not in params
    ):
        optional_settings["authenticator"] = "externalbrowser"

    params.update({key: value for key, value in optional_settings.items() if value})
    return params


def snowflake_connect():
    params = build_snowflake_params()

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