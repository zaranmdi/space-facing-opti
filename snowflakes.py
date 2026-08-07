from __future__ import annotations

import math
import os
from pathlib import Path

import pandas as pd
import snowflake.connector
from dotenv import load_dotenv

try:
    import plotly.graph_objects as go
except Exception:  # pragma: no cover - plotting is optional for data-only usage.
    go = None

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


def _sql_literal(value: str | int) -> str:
    if isinstance(value, int):
        return str(value)
    text = str(value).strip()
    return "'" + text.replace("'", "''") + "'"


def build_planogram_layout_sql(planogram_identifier: str | int) -> str:
    identifier = _sql_literal(planogram_identifier)
    return f"""
WITH latest_planogram AS (
    SELECT *
    FROM BDWPRD_SRCI.BLUEYONDER_CKB.IX_SPC_PLANOGRAM
    QUALIFY ROW_NUMBER() OVER (PARTITION BY DBKEY ORDER BY DW_STRT_TS DESC) = 1
),
latest_product AS (
    SELECT *
    FROM BDWPRD_SRCI.BLUEYONDER_CKB.IX_SPC_PRODUCT
    QUALIFY ROW_NUMBER() OVER (PARTITION BY DBKEY ORDER BY DW_STRT_TS DESC) = 1
),
latest_position AS (
    SELECT *
    FROM BDWPRD_SRCI.BLUEYONDER_CKB.IX_SPC_POSITION
    QUALIFY ROW_NUMBER() OVER (PARTITION BY DBKEY ORDER BY DW_STRT_TS DESC) = 1
)
SELECT
    pg.DBKEY AS PLANOGRAM_DBKEY,
    pg.ID AS PLANOGRAM_ID,
    pg.NAME AS PLANOGRAM_NAME,
    p.DBKEY AS POSITION_DBKEY,
    p.DBPARENTFIXTUREKEY,
    p.DBPARENTPRODUCTKEY,
    pr.ID AS PRODUCT_ID,
    pr.NAME AS PRODUCT_NAME,
    pr.BRAND AS PRODUCT_BRAND,
    p.MERCHSTYLE,
    p.FACINGS,
    p.HFACINGS,
    p.VFACINGS,
    p.CAPACITY,
    p.X,
    p.Y,
    p.Z,
    p.WIDTH,
    p.HEIGHT,
    p.DEPTH,
    p.ANGLE,
    p.MERCHXMIN,
    p.MERCHXMAX,
    p.MERCHYMIN,
    p.MERCHYMAX,
    p.MERCHZMIN,
    p.MERCHZMAX
FROM latest_position p
JOIN latest_planogram pg
    ON p.DBPARENTPLANOGRAMKEY = pg.DBKEY
LEFT JOIN latest_product pr
    ON p.DBPARENTPRODUCTKEY = pr.DBKEY
WHERE p.DW_REC_DEL_IND = FALSE
  AND pg.DW_REC_DEL_IND = FALSE
  AND COALESCE(pr.DW_REC_DEL_IND, FALSE) = FALSE
  AND (
        pg.ID = {identifier}
        OR CAST(pg.DBKEY AS VARCHAR) = {identifier}
      )
ORDER BY p.RANKY, p.RANKX, p.DBKEY
"""


def fetch_planogram_layout(
    conn,
    planogram_identifier: str | int,
) -> pd.DataFrame:
    frame = fetch_dataframe(conn, build_planogram_layout_sql(planogram_identifier))
    numeric_columns = [
        "X",
        "Y",
        "Z",
        "WIDTH",
        "HEIGHT",
        "DEPTH",
        "ANGLE",
        "FACINGS",
        "HFACINGS",
        "VFACINGS",
        "CAPACITY",
        "MERCHXMIN",
        "MERCHXMAX",
        "MERCHYMIN",
        "MERCHYMAX",
        "MERCHZMIN",
        "MERCHZMAX",
    ]
    for column in numeric_columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def prepare_planogram_layout_for_streamlit(layout_frame: pd.DataFrame) -> pd.DataFrame:
    prepared = layout_frame.copy()

    numeric_columns = ["X", "Y", "WIDTH", "HEIGHT", "CAPACITY", "FACINGS", "HFACINGS", "VFACINGS"]
    for column in numeric_columns:
        if column in prepared.columns:
            prepared[column] = pd.to_numeric(prepared[column], errors="coerce")

    rename_map = {
        "PRODUCT_ID": "ITEM_NUMBER",
        "PRODUCT_NAME": "ITEM_DESCRIPTION",
        "MERCHSTYLE": "MERCHANDISING_STYLE_CODE",
    }
    for source, target in rename_map.items():
        if source in prepared.columns and target not in prepared.columns:
            prepared[target] = prepared[source]

    required = ["PLANOGRAM_ID", "PLANOGRAM_NAME", "X", "Y", "WIDTH", "HEIGHT"]
    missing = [column for column in required if column not in prepared.columns]
    if missing:
        raise ValueError(
            "Missing required layout columns for Streamlit polygons: " + ", ".join(missing)
        )

    prepared["LAYOUT_GEOMETRY_VALID"] = (
        prepared["X"].notna()
        & prepared["Y"].notna()
        & prepared["WIDTH"].notna()
        & prepared["HEIGHT"].notna()
        & (prepared["WIDTH"] > 0)
        & (prepared["HEIGHT"] > 0)
    )
    return prepared


def fetch_planogram_item_geometry(
    conn,
    planogram_identifier: str | int,
) -> pd.DataFrame:
    """Return one geometry row per item-position with required layout columns first."""
    layout = fetch_planogram_layout(conn, planogram_identifier)
    prepared = prepare_planogram_layout_for_streamlit(layout)

    ordered_columns = [
        "PLANOGRAM_ID",
        "PLANOGRAM_NAME",
        "ITEM_NUMBER",
        "ITEM_DESCRIPTION",
        "MERCHANDISING_STYLE_CODE",
        "X",
        "Y",
        "WIDTH",
        "HEIGHT",
        "CAPACITY",
        "FACINGS",
        "HFACINGS",
        "VFACINGS",
        "SPACE_OPTIMIZATION_OPPORTUNITY",
        "LAYOUT_GEOMETRY_VALID",
    ]
    available_columns = [column for column in ordered_columns if column in prepared.columns]
    remaining_columns = [column for column in prepared.columns if column not in available_columns]
    geometry_frame = prepared[available_columns + remaining_columns].copy()

    dedupe_keys = [
        column
        for column in ["PLANOGRAM_ID", "ITEM_NUMBER", "MERCHANDISING_STYLE_CODE", "X", "Y", "WIDTH", "HEIGHT"]
        if column in geometry_frame.columns
    ]
    if dedupe_keys:
        geometry_frame = geometry_frame.drop_duplicates(subset=dedupe_keys, keep="first")

    return geometry_frame


def _rotate_points(
    points: list[tuple[float, float]],
    center_x: float,
    center_y: float,
    angle_degrees: float,
) -> list[tuple[float, float]]:
    angle_radians = math.radians(angle_degrees)
    cos_theta = math.cos(angle_radians)
    sin_theta = math.sin(angle_radians)
    rotated: list[tuple[float, float]] = []
    for x_coord, y_coord in points:
        translated_x = x_coord - center_x
        translated_y = y_coord - center_y
        rotated_x = translated_x * cos_theta - translated_y * sin_theta + center_x
        rotated_y = translated_x * sin_theta + translated_y * cos_theta + center_y
        rotated.append((rotated_x, rotated_y))
    return rotated


def build_position_polygon(position_row: pd.Series) -> list[tuple[float, float]]:
    has_explicit_bounds = pd.notna(position_row.get("MERCHXMIN")) and pd.notna(
        position_row.get("MERCHXMAX")
    ) and pd.notna(position_row.get("MERCHYMIN")) and pd.notna(
        position_row.get("MERCHYMAX")
    )

    if has_explicit_bounds:
        min_x = float(position_row["MERCHXMIN"])
        max_x = float(position_row["MERCHXMAX"])
        min_y = float(position_row["MERCHYMIN"])
        max_y = float(position_row["MERCHYMAX"])
        points = [
            (min_x, min_y),
            (max_x, min_y),
            (max_x, max_y),
            (min_x, max_y),
        ]
    else:
        # IX_SPC_POSITION X/Y represent bottom-left, not center coordinates.
        min_x = float(position_row.get("X", 0) or 0)
        min_y = float(position_row.get("Y", 0) or 0)
        width = float(position_row.get("WIDTH", 0) or 0)
        height = float(position_row.get("HEIGHT", 0) or 0)
        max_x = min_x + width
        max_y = min_y + height
        points = [
            (min_x, min_y),
            (max_x, min_y),
            (max_x, max_y),
            (min_x, max_y),
        ]

    angle = float(position_row.get("ANGLE", 0) or 0)
    if angle:
        center_x = sum(x for x, _ in points) / len(points)
        center_y = sum(y for _, y in points) / len(points)
        points = _rotate_points(points, center_x, center_y, angle)

    return points


def add_position_polygons(layout_frame: pd.DataFrame) -> pd.DataFrame:
    polygons = [build_position_polygon(row) for _, row in layout_frame.iterrows()]
    enriched = layout_frame.copy()
    enriched["POLYGON_POINTS"] = polygons
    enriched["POLYGON_X"] = [[point[0] for point in polygon] for polygon in polygons]
    enriched["POLYGON_Y"] = [[point[1] for point in polygon] for polygon in polygons]
    return enriched


def plot_planogram_layout(layout_frame: pd.DataFrame):
    if go is None:
        raise ImportError("plotly is required to plot planogram layouts")

    polygon_frame = add_position_polygons(layout_frame)
    figure = go.Figure()

    for _, row in polygon_frame.iterrows():
        polygon_x = row["POLYGON_X"] + [row["POLYGON_X"][0]]
        polygon_y = row["POLYGON_Y"] + [row["POLYGON_Y"][0]]
        hover_text = "<br>".join(
            [
                f"Planogram: {row.get('PLANOGRAM_ID', '')} - {row.get('PLANOGRAM_NAME', '')}",
                f"Product: {row.get('PRODUCT_ID', '')} - {row.get('PRODUCT_NAME', '')}",
                f"Facings: {row.get('FACINGS', '')}",
                f"H x V: {row.get('HFACINGS', '')} x {row.get('VFACINGS', '')}",
                f"X/Y: {row.get('X', '')}, {row.get('Y', '')}",
            ]
        )
        figure.add_trace(
            go.Scatter(
                x=polygon_x,
                y=polygon_y,
                mode="lines",
                fill="toself",
                line={"width": 1, "color": "#1f77b4"},
                fillcolor="rgba(31, 119, 180, 0.18)",
                name=str(row.get("PRODUCT_ID", row.get("POSITION_DBKEY", "Item"))),
                hovertext=hover_text,
                hoverinfo="text",
                showlegend=False,
            )
        )

        figure.add_trace(
            go.Scatter(
                x=[sum(row["POLYGON_X"]) / len(row["POLYGON_X"])],
                y=[sum(row["POLYGON_Y"]) / len(row["POLYGON_Y"])],
                mode="text",
                text=[str(row.get("PRODUCT_ID", ""))],
                textposition="middle center",
                hoverinfo="skip",
                showlegend=False,
            )
        )

    figure.update_layout(
        title=(
            f"Planogram Layout: {polygon_frame['PLANOGRAM_ID'].iloc[0]} - "
            f"{polygon_frame['PLANOGRAM_NAME'].iloc[0]}"
            if not polygon_frame.empty
            else "Planogram Layout"
        ),
        xaxis_title="X",
        yaxis_title="Y",
        xaxis={"scaleanchor": "y", "scaleratio": 1},
        yaxis={"autorange": "reversed"},
        template="plotly_white",
        margin={"l": 20, "r": 20, "t": 50, "b": 20},
    )
    return figure