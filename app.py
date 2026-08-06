from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from snowflakes import fetch_dataframe, snowflake_connect


SQL_FILE = "space_opti_code.sql"
STATUS_EXCLUSIONS = {
    "Deleted",
    "Quit (S1)",
    "Quit (S2)",
    "Quit (S3)",
    "Promotional",
    "De-Ranged",
    "Suspended",
    "Withdrawal",
    "Closed",
    "Promotion",
    "Archived",
}
OPPORTUNITY_OPTIONS = [
    "HIGH PRIORITY - ADD SPACE",
    "ADD SPACE / REVIEW",
    "SPACE DONOR - REDUCE SPACE",
    "HIGH WOS - REVIEW OVERSPACE",
    "NO SALES - REVIEW SPACE",
    "OK",
]
DEFAULT_OPPORTUNITIES = [value for value in OPPORTUNITY_OPTIONS if value != "OK"]
DATE_COLUMNS = [
    "SALES_START_DATE",
    "SALES_END_DATE",
    "FIRST_SALES_DATE",
    "EARLIEST_INVENTORY_STOCK_MOVEMENT_DATE",
    "ACTIVE_START_DATE",
]
NUMERIC_COLUMNS = [
    "ACTIVE_WEEKS",
    "MISSING_WEEKS",
    "CAPACITY",
    "PACK_ON_SHOW",
    "PLANOGRAM_CNT",
    "ACTUAL_SALES_QUANTITY",
    "ACTUAL_SALES_EXCLUDING_GST_52W",
    "INSTORE_SALES_QTY_52W",
    "ONLINE_SALES_QTY_52W",
    "UNK_SALES_QTY_52W",
    "FORECASTED_SALES_QUANTITY",
    "FORECASTED_SALES_EXCLUDING_GST",
    "FORECAST_ADJUSTED_QTY_52W",
    "FORECAST_ADJUSTED_SALES_AMOUNT_52W",
    "FORECAST_ADJUSTED_SALES_EXCLUDING_GST",
    "UNITSPSPW52",
    "WOS",
    "SALES_PER_CAPACITY_UNIT",
    "PRODUCTIVITY_RANK",
    "WOS_RANK",
]
BOOL_COLUMNS = [
    "IS_CLOSED",
    "LOW_WOS_FLAG",
    "LOW_PACK_ON_SHOW_FLAG",
    "NEEDS_MORE_SPACE_FLAG",
    "POSSIBLE_SPACE_DONOR_FLAG",
]
ITEM_LOCATION_KEY = ["DW_ITEM_ID", "DW_LOCATION_ID"]


st.set_page_config(
    page_title="Kitchen Space Optimisation Dashboard",
    page_icon=":bar_chart:",
    layout="wide",
)


def _normalise_bool(series: pd.Series) -> pd.Series:
    mapped = series.astype(str).str.strip().str.lower().map(
        {"true": True, "false": False, "1": True, "0": False}
    )
    return mapped.fillna(False)


def _sql_quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _sql_in_list(values: list[str]) -> str:
    return ", ".join(_sql_quote(value) for value in values)


def _parse_text_values(raw_value: str) -> list[str]:
    return [value.strip() for value in raw_value.split(",") if value.strip()]


def prepare_frame(frame: pd.DataFrame) -> pd.DataFrame:
    prepared = frame.copy()

    for column in DATE_COLUMNS:
        if column in prepared.columns:
            prepared[column] = pd.to_datetime(prepared[column], errors="coerce")

    for column in NUMERIC_COLUMNS:
        if column in prepared.columns:
            prepared[column] = pd.to_numeric(prepared[column], errors="coerce")

    for column in BOOL_COLUMNS:
        if column in prepared.columns:
            prepared[column] = _normalise_bool(prepared[column])

    for column in ["ITEM_NUMBER", "LOCATION_CODE", "PLANOGRAM_ID"]:
        if column in prepared.columns:
            prepared[column] = prepared[column].astype(str).str.strip()

    return prepared


def default_query_filters() -> dict[str, object]:
    return {
        "store_codes": "",
        "item_numbers": "",
        "item_search": "",
        "location_search": "",
        "planogram_search": "",
        "item_grades": "",
        "location_types": "",
        "opportunities": DEFAULT_OPPORTUNITIES,
        "min_active_weeks": 0,
        "include_closed": False,
        "include_excluded_statuses": False,
        "row_limit": 100000,
    }


def render_query_sidebar() -> dict[str, object]:
    saved_filters = st.session_state.get("query_filters", default_query_filters())

    with st.sidebar:
        st.header("Snowflake Query")
        st.caption("Queries run live against Snowflake using the SQL in space_opti_code.sql.")
        clear_cache = st.button("Clear cached query results")
        if clear_cache:
            st.cache_data.clear()

        with st.form("snowflake_filters"):
            opportunities = st.multiselect(
                "Opportunity",
                options=OPPORTUNITY_OPTIONS,
                default=saved_filters["opportunities"],
            )
            store_codes = st.text_input(
                "Store codes",
                value=str(saved_filters["store_codes"]),
                help="Comma-separated, for example 7152, 8103, 7379",
            )
            item_numbers = st.text_input(
                "Item numbers",
                value=str(saved_filters["item_numbers"]),
                help="Comma-separated exact item numbers",
            )
            item_search = st.text_input(
                "Item description contains",
                value=str(saved_filters["item_search"]),
            )
            location_search = st.text_input(
                "Store name contains",
                value=str(saved_filters["location_search"]),
            )
            planogram_search = st.text_input(
                "Planogram name contains",
                value=str(saved_filters["planogram_search"]),
            )
            item_grades = st.text_input(
                "Item grades",
                value=str(saved_filters["item_grades"]),
                help="Comma-separated, for example A, B, C, D",
            )
            location_types = st.text_input(
                "Location types",
                value=str(saved_filters["location_types"]),
                help="Comma-separated location type codes",
            )
            min_active_weeks = st.slider(
                "Minimum active weeks",
                min_value=0,
                max_value=52,
                value=int(saved_filters["min_active_weeks"]),
            )
            row_limit = st.number_input(
                "Row limit",
                min_value=1000,
                max_value=500000,
                value=int(saved_filters["row_limit"]),
                step=1000,
                help="Caps the returned Snowflake result set for responsiveness.",
            )
            include_closed = st.toggle(
                "Include closed locations",
                value=bool(saved_filters["include_closed"]),
            )
            include_excluded_statuses = st.toggle(
                "Include excluded statuses",
                value=bool(saved_filters["include_excluded_statuses"]),
            )
            submitted = st.form_submit_button("Run Snowflake query")

    current_filters = {
        "store_codes": store_codes,
        "item_numbers": item_numbers,
        "item_search": item_search,
        "location_search": location_search,
        "planogram_search": planogram_search,
        "item_grades": item_grades,
        "location_types": location_types,
        "opportunities": opportunities,
        "min_active_weeks": min_active_weeks,
        "include_closed": include_closed,
        "include_excluded_statuses": include_excluded_statuses,
        "row_limit": int(row_limit),
    }

    if submitted or "query_filters" not in st.session_state:
        st.session_state["query_filters"] = current_filters

    return st.session_state["query_filters"]


def build_live_sql(base_sql: str, filters: dict[str, object]) -> str:
    predicates: list[str] = []

    opportunities = [value for value in filters["opportunities"] if value]
    if opportunities:
        predicates.append(
            f"SPACE_OPTIMIZATION_OPPORTUNITY IN ({_sql_in_list(opportunities)})"
        )

    if not filters["include_excluded_statuses"]:
        predicates.append(
            f"CURRENT_ITEM_STATUS_CODE NOT IN ({_sql_in_list(sorted(STATUS_EXCLUSIONS))})"
        )

    if not filters["include_closed"]:
        predicates.append("COALESCE(IS_CLOSED, FALSE) = FALSE")

    if int(filters["min_active_weeks"]):
        predicates.append(f"COALESCE(ACTIVE_WEEKS, 0) >= {int(filters['min_active_weeks'])}")

    store_codes = _parse_text_values(str(filters["store_codes"]))
    if store_codes:
        predicates.append(f"LOCATION_CODE IN ({_sql_in_list(store_codes)})")

    item_numbers = _parse_text_values(str(filters["item_numbers"]))
    if item_numbers:
        predicates.append(f"ITEM_NUMBER IN ({_sql_in_list(item_numbers)})")

    item_grades = _parse_text_values(str(filters["item_grades"]))
    if item_grades:
        predicates.append(f"ITEM_GRADE IN ({_sql_in_list(item_grades)})")

    location_types = _parse_text_values(str(filters["location_types"]))
    if location_types:
        predicates.append(f"LOCATION_TYPE_CODE IN ({_sql_in_list(location_types)})")

    if filters["item_search"]:
        predicates.append(
            f"ITEM_DESCRIPTION ILIKE {_sql_quote('%' + str(filters['item_search']).strip() + '%')}"
        )

    if filters["location_search"]:
        predicates.append(
            f"LOCATION_NAME ILIKE {_sql_quote('%' + str(filters['location_search']).strip() + '%')}"
        )

    if filters["planogram_search"]:
        predicates.append(
            f"PLANOGRAM_NAME ILIKE {_sql_quote('%' + str(filters['planogram_search']).strip() + '%')}"
        )

    clean_sql = base_sql.rstrip().rstrip(";").rstrip()
    wrapped_sql = f"SELECT * FROM (\n{clean_sql}\n) dashboard"
    if predicates:
        wrapped_sql += "\nWHERE " + "\n  AND ".join(predicates)

    wrapped_sql += (
        "\nORDER BY DW_PLANOGRAM_ID, DW_LOCATION_ID, SALES_PER_CAPACITY_UNIT DESC"
    )
    wrapped_sql += f"\nLIMIT {int(filters['row_limit'])}"
    return wrapped_sql


@st.cache_data(show_spinner="Running Snowflake query...")
def fetch_live_dataset(sql_text: str) -> pd.DataFrame:
    conn = snowflake_connect()
    try:
        frame = fetch_dataframe(conn, sql_text)
    finally:
        conn.close()
    return prepare_frame(frame)


def build_item_location_view(frame: pd.DataFrame) -> pd.DataFrame:
    if not set(ITEM_LOCATION_KEY).issubset(frame.columns):
        return frame.copy()

    preferred_order = [
        "NEEDS_MORE_SPACE_FLAG",
        "POSSIBLE_SPACE_DONOR_FLAG",
        "LOW_WOS_FLAG",
        "LOW_PACK_ON_SHOW_FLAG",
        "ACTUAL_SALES_EXCLUDING_GST_52W",
    ]
    available_order = [column for column in preferred_order if column in frame.columns]
    ranked = (
        frame.sort_values(available_order, ascending=[False] * len(available_order))
        if available_order
        else frame.copy()
    )
    deduped = ranked.drop_duplicates(subset=ITEM_LOCATION_KEY, keep="first").copy()
    item_number = deduped["ITEM_NUMBER"].astype(str) if "ITEM_NUMBER" in deduped.columns else ""
    item_description = deduped["ITEM_DESCRIPTION"].astype(str) if "ITEM_DESCRIPTION" in deduped.columns else ""
    location_code = deduped["LOCATION_CODE"].astype(str) if "LOCATION_CODE" in deduped.columns else ""
    deduped["ITEM_LOCATION_LABEL"] = item_number + " | " + item_description + " | " + location_code
    return deduped


def metric_card_columns(item_location_frame: pd.DataFrame, row_frame: pd.DataFrame) -> None:
    needs_more = int(item_location_frame.get("NEEDS_MORE_SPACE_FLAG", pd.Series(dtype=bool)).fillna(False).sum())
    donors = int(item_location_frame.get("POSSIBLE_SPACE_DONOR_FLAG", pd.Series(dtype=bool)).fillna(False).sum())
    low_wos = int(item_location_frame.get("LOW_WOS_FLAG", pd.Series(dtype=bool)).fillna(False).sum())

    sales_value = item_location_frame.get("ACTUAL_SALES_EXCLUDING_GST_52W", pd.Series(dtype=float)).fillna(0).sum()
    item_locations = item_location_frame[ITEM_LOCATION_KEY].drop_duplicates().shape[0] if set(ITEM_LOCATION_KEY).issubset(item_location_frame.columns) else len(item_location_frame)
    planograms = row_frame["DW_PLANOGRAM_ID"].nunique() if "DW_PLANOGRAM_ID" in row_frame.columns else 0

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Item-locations", f"{item_locations:,}")
    col2.metric("Planograms", f"{planograms:,}")
    col3.metric("Needs more space", f"{needs_more:,}")
    col4.metric("Possible donors", f"{donors:,}")
    col5.metric("Actual sales ex GST", f"${sales_value:,.0f}")

    st.caption(f"Low WOS item-locations: {low_wos:,}. KPI measures use a deduped item-location view to avoid double-counting duplicated merchandising-style rows.")


def render_overview(item_location_frame: pd.DataFrame, row_frame: pd.DataFrame) -> None:
    metric_card_columns(item_location_frame, row_frame)

    chart_left, chart_right = st.columns(2)

    with chart_left:
        opp_counts = (
            item_location_frame["SPACE_OPTIMIZATION_OPPORTUNITY"].fillna("Unlabelled").value_counts().rename_axis("Opportunity").reset_index(name="Item locations")
        )
        fig = px.bar(
            opp_counts,
            x="Item locations",
            y="Opportunity",
            orientation="h",
            title="Opportunity mix",
            color="Opportunity",
        )
        fig.update_layout(showlegend=False, height=430)
        st.plotly_chart(fig, use_container_width=True)

    with chart_right:
        scatter = item_location_frame.copy()
        scatter["Opportunity"] = scatter["SPACE_OPTIMIZATION_OPPORTUNITY"].fillna("Unlabelled")
        fig = px.scatter(
            scatter,
            x="WOS",
            y="SALES_PER_CAPACITY_UNIT",
            size="ACTUAL_SALES_QUANTITY",
            color="Opportunity",
            hover_data=["ITEM_NUMBER", "ITEM_DESCRIPTION", "LOCATION_NAME", "PLANOGRAM_NAME"],
            title="WOS vs sales per capacity unit",
            height=430,
        )
        st.plotly_chart(fig, use_container_width=True)

    lower_left, lower_right = st.columns(2)
    with lower_left:
        top_stores = (
            item_location_frame.groupby(["LOCATION_CODE", "LOCATION_NAME"], dropna=False)
            .agg(
                item_locations=("DW_ITEM_ID", "count"),
                needs_more_space=("NEEDS_MORE_SPACE_FLAG", "sum"),
                possible_donors=("POSSIBLE_SPACE_DONOR_FLAG", "sum"),
                sales=("ACTUAL_SALES_EXCLUDING_GST_52W", "sum"),
            )
            .reset_index()
            .sort_values("needs_more_space", ascending=False)
            .head(15)
        )
        fig = px.bar(
            top_stores,
            x="needs_more_space",
            y="LOCATION_NAME",
            orientation="h",
            hover_data=["LOCATION_CODE", "item_locations", "possible_donors", "sales"],
            title="Stores with the most space-add opportunities",
            height=500,
        )
        st.plotly_chart(fig, use_container_width=True)

    with lower_right:
        top_planograms = (
            item_location_frame.groupby("PLANOGRAM_NAME", dropna=False)
            .agg(
                item_locations=("DW_ITEM_ID", "count"),
                needs_more_space=("NEEDS_MORE_SPACE_FLAG", "sum"),
                possible_donors=("POSSIBLE_SPACE_DONOR_FLAG", "sum"),
            )
            .reset_index()
            .sort_values("needs_more_space", ascending=False)
            .head(15)
        )
        fig = px.bar(
            top_planograms,
            x="needs_more_space",
            y="PLANOGRAM_NAME",
            orientation="h",
            hover_data=["item_locations", "possible_donors"],
            title="Planograms with the most space-add opportunities",
            height=500,
        )
        st.plotly_chart(fig, use_container_width=True)


def render_opportunity_table(item_location_frame: pd.DataFrame) -> None:
    ranked = item_location_frame.copy()
    ranked["opportunity_sort"] = ranked["NEEDS_MORE_SPACE_FLAG"].fillna(False).astype(int) * 2 + ranked["POSSIBLE_SPACE_DONOR_FLAG"].fillna(False).astype(int)
    ranked = ranked.sort_values(
        ["opportunity_sort", "SALES_PER_CAPACITY_UNIT", "ACTUAL_SALES_EXCLUDING_GST_52W"],
        ascending=[False, True, False],
    )

    columns = [
        "SPACE_OPTIMIZATION_OPPORTUNITY",
        "ITEM_NUMBER",
        "ITEM_DESCRIPTION",
        "ITEM_GRADE",
        "LOCATION_CODE",
        "LOCATION_NAME",
        "PLANOGRAM_NAME",
        "CURRENT_ITEM_STATUS_CODE",
        "CAPACITY",
        "PACK_ON_SHOW",
        "WOS",
        "SALES_PER_CAPACITY_UNIT",
        "ACTUAL_SALES_QUANTITY",
        "ACTUAL_SALES_EXCLUDING_GST_52W",
        "FORECAST_ADJUSTED_QTY_52W",
        "NEEDS_MORE_SPACE_FLAG",
        "POSSIBLE_SPACE_DONOR_FLAG",
    ]
    visible_columns = [column for column in columns if column in ranked.columns]
    st.dataframe(ranked[visible_columns], use_container_width=True, height=620)


def render_planogram_summary(item_location_frame: pd.DataFrame) -> None:
    summary = (
        item_location_frame.groupby(
            ["PLANOGRAM_ID", "PLANOGRAM_NAME", "PLANOGRAM_DEPARTMENT_NAME"],
            dropna=False,
        )
        .agg(
            item_locations=("DW_ITEM_ID", "count"),
            stores=("DW_LOCATION_ID", "nunique"),
            needs_more_space=("NEEDS_MORE_SPACE_FLAG", "sum"),
            possible_donors=("POSSIBLE_SPACE_DONOR_FLAG", "sum"),
            actual_sales=("ACTUAL_SALES_EXCLUDING_GST_52W", "sum"),
            avg_wos=("WOS", "mean"),
        )
        .reset_index()
        .sort_values(["needs_more_space", "actual_sales"], ascending=[False, False])
    )
    st.dataframe(summary, use_container_width=True, height=620)


def render_store_summary(item_location_frame: pd.DataFrame) -> None:
    summary = (
        item_location_frame.groupby(["LOCATION_CODE", "LOCATION_NAME", "LOCATION_TYPE_CODE"], dropna=False)
        .agg(
            item_locations=("DW_ITEM_ID", "count"),
            planograms=("PLANOGRAM_ID", "nunique"),
            needs_more_space=("NEEDS_MORE_SPACE_FLAG", "sum"),
            possible_donors=("POSSIBLE_SPACE_DONOR_FLAG", "sum"),
            low_wos=("LOW_WOS_FLAG", "sum"),
            sales=("ACTUAL_SALES_EXCLUDING_GST_52W", "sum"),
        )
        .reset_index()
        .sort_values(["needs_more_space", "sales"], ascending=[False, False])
    )
    st.dataframe(summary, use_container_width=True, height=620)


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    sql_path = base_dir / SQL_FILE

    st.title("Kitchen Space Optimisation Dashboard")
    st.caption(
        "Interactive review of space optimisation outputs across planograms, stores, and item-locations. "
        "The app now queries Snowflake live and applies the notebook's inactive-status exclusions by default."
    )

    query_filters = render_query_sidebar()

    if not sql_path.exists():
        st.error(f"SQL file not found: {sql_path}")
        return

    base_sql = sql_path.read_text(encoding="utf-8")
    live_sql = build_live_sql(base_sql, query_filters)

    with st.expander("Current Snowflake query settings", expanded=False):
        st.write({
            "store_codes": query_filters["store_codes"],
            "item_numbers": query_filters["item_numbers"],
            "item_search": query_filters["item_search"],
            "location_search": query_filters["location_search"],
            "planogram_search": query_filters["planogram_search"],
            "item_grades": query_filters["item_grades"],
            "location_types": query_filters["location_types"],
            "opportunities": query_filters["opportunities"],
            "min_active_weeks": query_filters["min_active_weeks"],
            "include_closed": query_filters["include_closed"],
            "include_excluded_statuses": query_filters["include_excluded_statuses"],
            "row_limit": query_filters["row_limit"],
        })

    frame = fetch_live_dataset(live_sql)

    if len(frame) >= int(query_filters["row_limit"]):
        st.warning(
            "The returned dataset hit the configured row limit. Narrow the Snowflake filters or increase the cap before treating the dashboard totals as complete."
        )

    filtered_rows = frame
    item_location_view = build_item_location_view(frame)

    if filtered_rows.empty:
        st.warning("No rows match the current filters.")
        return

    overview_tab, opportunities_tab, planograms_tab, stores_tab, raw_tab = st.tabs(
        ["Overview", "Opportunities", "Planograms", "Stores", "Raw data"]
    )

    with overview_tab:
        render_overview(item_location_view, filtered_rows)

    with opportunities_tab:
        render_opportunity_table(item_location_view)

    with planograms_tab:
        render_planogram_summary(item_location_view)

    with stores_tab:
        render_store_summary(item_location_view)

    with raw_tab:
        st.caption("Raw row-level view. This includes merchandising-style duplicates from the export.")
        st.dataframe(filtered_rows, use_container_width=True, height=620)
        st.download_button(
            "Download filtered rows as CSV",
            filtered_rows.to_csv(index=False).encode("utf-8"),
            file_name="space_optimisation_filtered.csv",
            mime="text/csv",
        )


if __name__ == "__main__":
    main()