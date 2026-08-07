from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

try:
    from st_aggrid import AgGrid, GridOptionsBuilder
except Exception:  # pragma: no cover - fallback when dependency is unavailable.
    AgGrid = None
    GridOptionsBuilder = None


PREFERRED_DATASET_NAME = "samp_2026-08-07-1232.csv"
DATA_GLOB = "space_opt_2_*.csv"
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
OPPORTUNITY_COLOR_MAP = {
    "HIGH PRIORITY - ADD SPACE": "#d73027",
    "ADD SPACE / REVIEW": "#fc8d59",
    "SPACE DONOR - REDUCE SPACE": "#4575b4",
    "HIGH WOS - REVIEW OVERSPACE": "#6a3d9a",
    "NO SALES - REVIEW SPACE": "#1f78b4",
    "OK": "#4d4d4d",
    "Unlabelled": "#7f7f7f",
}
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
PLANOGRAM_ITEM_LOCATION_KEY = ["DW_PLANOGRAM_ID", "DW_ITEM_ID", "DW_LOCATION_ID"]


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


def find_latest_dataset(base_dir: Path) -> Path | None:
    preferred_dataset = base_dir / PREFERRED_DATASET_NAME
    if preferred_dataset.exists():
        return preferred_dataset

    matches = sorted(base_dir.glob(DATA_GLOB), key=lambda path: path.stat().st_mtime)
    return matches[-1] if matches else None


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


@st.cache_data(show_spinner=False)
def load_dataset(source_name: str, file_bytes: bytes | None = None) -> pd.DataFrame:
    if file_bytes is None and source_name.lower().endswith(".xlsx"):
        frame = pd.read_excel(source_name)
    elif file_bytes is None:
        frame = pd.read_csv(source_name, low_memory=False)
    elif source_name.lower().endswith(".xlsx"):
        frame = pd.read_excel(pd.io.common.BytesIO(file_bytes))
    else:
        frame = pd.read_csv(pd.io.common.BytesIO(file_bytes), low_memory=False)

    return prepare_frame(frame)


def filter_frame(frame: pd.DataFrame) -> pd.DataFrame:
    with st.sidebar:
        st.header("Filters")

        opportunity_options = sorted(frame["SPACE_OPTIMIZATION_OPPORTUNITY"].dropna().unique())
        status_options = sorted(frame["CURRENT_ITEM_STATUS_CODE"].dropna().unique())
        grade_options = sorted(frame["ITEM_GRADE"].dropna().unique()) if "ITEM_GRADE" in frame.columns else []
        planogram_options = sorted(frame["PLANOGRAM_NAME"].dropna().unique()) if "PLANOGRAM_NAME" in frame.columns else []
        department_options = sorted(frame["PLANOGRAM_DEPARTMENT_NAME"].dropna().unique()) if "PLANOGRAM_DEPARTMENT_NAME" in frame.columns else []
        location_type_options = sorted(frame["LOCATION_TYPE_CODE"].dropna().unique()) if "LOCATION_TYPE_CODE" in frame.columns else []
        style_options = sorted(frame["MERCHANDISING_STYLE_CODE"].dropna().unique()) if "MERCHANDISING_STYLE_CODE" in frame.columns else []
        sales_channel_options = [
            option
            for option in ["In-store", "Online"]
            if (
                (option == "In-store" and "INSTORE_SALES_QTY_52W" in frame.columns)
                or (option == "Online" and "ONLINE_SALES_QTY_52W" in frame.columns)
            )
        ]

        selected_opportunities = st.multiselect(
            "Opportunity",
            options=opportunity_options,
            default=[value for value in DEFAULT_OPPORTUNITIES if value in opportunity_options],
        )
        selected_statuses = st.multiselect(
            "Current status",
            options=status_options,
            default=[value for value in status_options if value not in STATUS_EXCLUSIONS],
        )
        selected_grades = st.multiselect("Item grade", options=grade_options, default=grade_options)
        selected_departments = st.multiselect(
            "Department",
            options=department_options,
            default=department_options,
        )
        selected_styles = st.multiselect(
            "Display / style",
            options=style_options,
            default=style_options,
        )
        selected_location_types = st.multiselect(
            "Location type",
            options=location_type_options,
            default=location_type_options,
        )
        selected_planograms = st.multiselect(
            "Planogram name",
            options=planogram_options,
            default=[],
            placeholder="All planograms",
        )
        store_search = st.text_input("Store code or name contains")
        item_search = st.text_input("Item number or description contains")
        selected_sales_channels = st.multiselect(
            "Sales channel activity",
            options=sales_channel_options,
            default=sales_channel_options,
        )
        active_weeks = st.slider(
            "Minimum active weeks",
            min_value=0,
            max_value=52,
            value=0,
        )
        include_closed = st.toggle("Include closed locations", value=False)

    filtered = frame.copy()

    if selected_opportunities:
        filtered = filtered[filtered["SPACE_OPTIMIZATION_OPPORTUNITY"].isin(selected_opportunities)]
    if selected_statuses:
        filtered = filtered[filtered["CURRENT_ITEM_STATUS_CODE"].isin(selected_statuses)]
    if selected_grades and "ITEM_GRADE" in filtered.columns:
        filtered = filtered[filtered["ITEM_GRADE"].isin(selected_grades)]
    if selected_departments and "PLANOGRAM_DEPARTMENT_NAME" in filtered.columns:
        filtered = filtered[filtered["PLANOGRAM_DEPARTMENT_NAME"].isin(selected_departments)]
    if selected_styles and "MERCHANDISING_STYLE_CODE" in filtered.columns:
        filtered = filtered[filtered["MERCHANDISING_STYLE_CODE"].isin(selected_styles)]
    if selected_location_types and "LOCATION_TYPE_CODE" in filtered.columns:
        filtered = filtered[filtered["LOCATION_TYPE_CODE"].isin(selected_location_types)]
    if selected_planograms and "PLANOGRAM_NAME" in filtered.columns:
        filtered = filtered[filtered["PLANOGRAM_NAME"].isin(selected_planograms)]
    if selected_sales_channels and len(selected_sales_channels) != len(sales_channel_options):
        channel_masks: list[pd.Series] = []
        if "In-store" in selected_sales_channels and "INSTORE_SALES_QTY_52W" in filtered.columns:
            channel_masks.append(filtered["INSTORE_SALES_QTY_52W"].fillna(0) > 0)
        if "Online" in selected_sales_channels and "ONLINE_SALES_QTY_52W" in filtered.columns:
            channel_masks.append(filtered["ONLINE_SALES_QTY_52W"].fillna(0) > 0)
        if channel_masks:
            combined_mask = channel_masks[0]
            for mask in channel_masks[1:]:
                combined_mask = combined_mask | mask
            filtered = filtered[combined_mask]
    if "ACTIVE_WEEKS" in filtered.columns:
        filtered = filtered[filtered["ACTIVE_WEEKS"].fillna(0) >= active_weeks]
    if not include_closed and "IS_CLOSED" in filtered.columns:
        filtered = filtered[~filtered["IS_CLOSED"].fillna(False)]

    if store_search:
        store_term = store_search.strip().lower()
        filtered = filtered[
            filtered["LOCATION_NAME"].fillna("").str.lower().str.contains(store_term)
            | filtered["LOCATION_CODE"].fillna("").astype(str).str.lower().str.contains(store_term)
        ]
    if item_search:
        item_term = item_search.strip().lower()
        filtered = filtered[
            filtered["ITEM_DESCRIPTION"].fillna("").str.lower().str.contains(item_term)
            | filtered["ITEM_NUMBER"].fillna("").astype(str).str.lower().str.contains(item_term)
        ]

    return filtered


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


def build_planogram_item_location_view(frame: pd.DataFrame) -> pd.DataFrame:
    if not set(PLANOGRAM_ITEM_LOCATION_KEY).issubset(frame.columns):
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
    return ranked.drop_duplicates(subset=PLANOGRAM_ITEM_LOCATION_KEY, keep="first").copy()


def _first_existing_column(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in frame.columns:
            return candidate
    return None


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    color = (hex_color or "").strip().lstrip("#")
    if len(color) != 6:
        return f"rgba(127,127,127,{alpha})"
    red = int(color[0:2], 16)
    green = int(color[2:4], 16)
    blue = int(color[4:6], 16)
    return f"rgba({red},{green},{blue},{alpha})"


def render_planogram_layout(row_frame: pd.DataFrame) -> None:
    if row_frame.empty:
        st.warning("No rows match the current filters.")
        return

    x_col = _first_existing_column(row_frame, ["X", "x"])
    y_col = _first_existing_column(row_frame, ["Y", "y"])
    width_col = _first_existing_column(row_frame, ["WIDTH", "width"])
    height_col = _first_existing_column(row_frame, ["HEIGHT", "height"])

    required_cols = [x_col, y_col, width_col, height_col]
    if any(column is None for column in required_cols):
        missing = [
            name
            for name, column in {
                "X": x_col,
                "Y": y_col,
                "WIDTH": width_col,
                "HEIGHT": height_col,
            }.items()
            if column is None
        ]
        st.warning(
            "Layout columns are missing in the current dataset: "
            + ", ".join(missing)
            + "."
        )
        st.caption(
            "Refresh your extract to include ix_spc_position coordinates so this tab can render product blocks."
        )
        return

    if "PLANOGRAM_ID" not in row_frame.columns:
        st.warning("PLANOGRAM_ID is missing in the current dataset, so planogram layout cannot be filtered.")
        return

    layout = row_frame.copy()
    layout["PLANOGRAM_ID"] = layout["PLANOGRAM_ID"].astype(str).str.strip()
    if "PLANOGRAM_NAME" in layout.columns:
        layout["PLANOGRAM_NAME"] = layout["PLANOGRAM_NAME"].fillna("").astype(str).str.strip()
    else:
        layout["PLANOGRAM_NAME"] = ""

    layout["PLANOGRAM_LABEL"] = layout["PLANOGRAM_ID"] + " - " + layout["PLANOGRAM_NAME"]
    planogram_labels = sorted(label for label in layout["PLANOGRAM_LABEL"].dropna().unique() if str(label).strip())
    if not planogram_labels:
        st.warning("No planograms are available after filtering.")
        return

    selected_planogram = st.selectbox(
        "Choose planogram",
        options=planogram_labels,
        key="planogram_layout_selector",
    )

    selected = layout[layout["PLANOGRAM_LABEL"] == selected_planogram].copy()
    selected["_x"] = pd.to_numeric(selected[x_col], errors="coerce")
    selected["_y"] = pd.to_numeric(selected[y_col], errors="coerce")
    selected["_w"] = pd.to_numeric(selected[width_col], errors="coerce")
    selected["_h"] = pd.to_numeric(selected[height_col], errors="coerce")

    selected = selected[
        selected["_x"].notna()
        & selected["_y"].notna()
        & selected["_w"].notna()
        & selected["_h"].notna()
        & (selected["_w"] > 0)
        & (selected["_h"] > 0)
    ]

    if selected.empty:
        st.warning("No valid geometry rows were found for the selected planogram.")
        return

    selected["_x2"] = selected["_x"] + selected["_w"]
    selected["_y2"] = selected["_y"] + selected["_h"]

    show_labels = st.toggle("Show item labels", value=False, key="planogram_layout_show_labels")
    figure = go.Figure()

    for _, row in selected.iterrows():
        x0 = float(row["_x"])
        y0 = float(row["_y"])
        x1 = float(row["_x2"])
        y1 = float(row["_y2"])
        xs = [x0, x1, x1, x0, x0]
        ys = [y0, y0, y1, y1, y0]

        opportunity = row.get("SPACE_OPTIMIZATION_OPPORTUNITY", "Unlabelled")
        base_color = OPPORTUNITY_COLOR_MAP.get(opportunity, OPPORTUNITY_COLOR_MAP["Unlabelled"])
        item_number = str(row.get("ITEM_NUMBER", ""))
        item_description = str(row.get("ITEM_DESCRIPTION", ""))
        style = str(row.get("MERCHANDISING_STYLE_CODE", ""))
        facings = row.get("CAPACITY", "")

        hover_template = (
            f"<b>{item_number}</b><br>"
            f"{item_description}<br>"
            f"Style: {style}<br>"
            f"Capacity: {facings}<br>"
            f"Opportunity: {opportunity}<br>"
            f"X,Y: ({x0:.2f}, {y0:.2f})<br>"
            f"W,H: ({float(row['_w']):.2f}, {float(row['_h']):.2f})"
            "<extra></extra>"
        )

        figure.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines",
                line={"width": 1, "color": base_color},
                fill="toself",
                fillcolor=_hex_to_rgba(base_color, 0.25),
                hovertemplate=hover_template,
                showlegend=False,
            )
        )

        if show_labels:
            figure.add_trace(
                go.Scatter(
                    x=[x0 + (x1 - x0) / 2],
                    y=[y0 + (y1 - y0) / 2],
                    mode="text",
                    text=[item_number],
                    textfont={"size": 9},
                    hoverinfo="skip",
                    showlegend=False,
                )
            )

    figure.update_layout(
        title=f"2D Product Layout | {selected_planogram}",
        xaxis_title="X",
        yaxis_title="Y",
        xaxis={"scaleanchor": "y", "scaleratio": 1},
        template="plotly_white",
        height=760,
        margin={"l": 20, "r": 20, "t": 60, "b": 20},
    )
    st.plotly_chart(figure, use_container_width=True)
    st.caption(
        f"Rendered {len(selected):,} product blocks using bottom-left coordinates with width/height from ix_spc_position."
    )


def render_filterable_table(
    frame: pd.DataFrame,
    *,
    height: int = 620,
    key: str,
) -> None:
    if AgGrid is None or GridOptionsBuilder is None:
        st.info("Install `streamlit-aggrid` to enable per-column table filters.")
        st.dataframe(frame, width="stretch", height=height)
        return

    grid_builder = GridOptionsBuilder.from_dataframe(frame)
    grid_builder.configure_default_column(
        sortable=True,
        filter=True,
        floatingFilter=True,
        resizable=True,
    )
    grid_builder.configure_grid_options(
        animateRows=False,
        suppressFieldDotNotation=True,
    )
    AgGrid(
        frame,
        gridOptions=grid_builder.build(),
        theme="streamlit",
        height=height,
        fit_columns_on_grid_load=False,
        allow_unsafe_jscode=False,
        key=key,
    )


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


def render_overview(
    item_location_frame: pd.DataFrame,
    planogram_frame: pd.DataFrame,
    row_frame: pd.DataFrame,
) -> None:
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
            color_discrete_map=OPPORTUNITY_COLOR_MAP,
        )
        fig.update_layout(showlegend=False, height=430)
        st.plotly_chart(fig, use_container_width=True)

    with chart_right:
        scatter = item_location_frame.copy()
        scatter["Opportunity"] = scatter["SPACE_OPTIMIZATION_OPPORTUNITY"].fillna("Unlabelled")
        scatter["ACTUAL_SALES_SIZE"] = (
            pd.to_numeric(scatter["ACTUAL_SALES_QUANTITY"], errors="coerce")
            .fillna(0)
            .clip(lower=0)
        )
        fig = px.scatter(
            scatter,
            x="WOS",
            y="SALES_PER_CAPACITY_UNIT",
            size="ACTUAL_SALES_SIZE",
            color="Opportunity",
            color_discrete_map=OPPORTUNITY_COLOR_MAP,
            hover_data=[
                "ITEM_NUMBER",
                "ITEM_DESCRIPTION",
                "LOCATION_NAME",
                "PLANOGRAM_NAME",
                "ACTUAL_SALES_QUANTITY",
            ],
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
        sales_channel_totals = pd.DataFrame(
            {
                "Channel": ["In-store", "Online"],
                "Sales Qty 52W": [
                    item_location_frame.get("INSTORE_SALES_QTY_52W", pd.Series(dtype=float)).fillna(0).sum(),
                    item_location_frame.get("ONLINE_SALES_QTY_52W", pd.Series(dtype=float)).fillna(0).sum(),
                ],
            }
        )
        fig = px.bar(
            sales_channel_totals,
            x="Channel",
            y="Sales Qty 52W",
            color="Channel",
            title="In-store vs online sales quantity",
            height=500,
        )
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    planogram_left, planogram_right = st.columns(2)
    top_planograms = (
        planogram_frame.groupby(["PLANOGRAM_ID", "PLANOGRAM_NAME"], dropna=False)
        .agg(
            item_locations=("DW_ITEM_ID", "count"),
            needs_more_space=("NEEDS_MORE_SPACE_FLAG", "sum"),
            possible_donors=("POSSIBLE_SPACE_DONOR_FLAG", "sum"),
        )
        .reset_index()
    )
    top_planograms["PLANOGRAM_LABEL"] = (
        top_planograms["PLANOGRAM_ID"].astype(str).fillna("")
        + " - "
        + top_planograms["PLANOGRAM_NAME"].astype(str).fillna("")
    )

    with planogram_left:
        add_space_planograms = (
            top_planograms.sort_values("needs_more_space", ascending=False).head(15)
        )
        fig = px.bar(
            add_space_planograms,
            x="needs_more_space",
            y="PLANOGRAM_LABEL",
            orientation="h",
            hover_data=["item_locations", "possible_donors"],
            title="Planograms with the most space-add opportunities",
            height=500,
        )
        st.plotly_chart(fig, use_container_width=True)

    with planogram_right:
        reduce_space_planograms = (
            top_planograms.sort_values("possible_donors", ascending=False).head(15)
        )
        fig = px.bar(
            reduce_space_planograms,
            x="possible_donors",
            y="PLANOGRAM_LABEL",
            orientation="h",
            hover_data=["item_locations", "needs_more_space"],
            title="Planograms with the most space-reduce opportunities",
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
        "PLANOGRAM_DEPARTMENT_NAME",
        "MERCHANDISING_STYLE_CODE",
        "LOCATION_CODE",
        "LOCATION_NAME",
        "PLANOGRAM_NAME",
        "CURRENT_ITEM_STATUS_CODE",
        "CAPACITY",
        "PACK_ON_SHOW",
        "WOS",
        "SALES_PER_CAPACITY_UNIT",
        "ACTUAL_SALES_QUANTITY",
        "INSTORE_SALES_QTY_52W",
        "ONLINE_SALES_QTY_52W",
        "ACTUAL_SALES_EXCLUDING_GST_52W",
        "FORECAST_ADJUSTED_QTY_52W",
        "NEEDS_MORE_SPACE_FLAG",
        "POSSIBLE_SPACE_DONOR_FLAG",
    ]
    visible_columns = [column for column in columns if column in ranked.columns]
    render_filterable_table(
        ranked[visible_columns],
        height=620,
        key="opportunities_table",
    )


def render_planogram_summary(planogram_frame: pd.DataFrame) -> None:
    summary = (
        planogram_frame.groupby(
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
    render_filterable_table(summary, height=620, key="planogram_summary_table")


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
    render_filterable_table(summary, height=620, key="store_summary_table")


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    latest_dataset = find_latest_dataset(base_dir)

    st.title("Kitchen Space Optimisation Dashboard")
    st.caption(
        "Interactive review of space optimisation outputs across planograms, stores, and item-locations. "
        "The app uses a local optimisation extract or an uploaded file and applies the notebook's inactive-status exclusions by default."
    )

    with st.sidebar:
        st.header("Source")
        uploaded_file = st.file_uploader("Upload optimisation extract", type=["csv", "xlsx"])
        source_label = uploaded_file.name if uploaded_file is not None else (latest_dataset.name if latest_dataset else "No local extract found")
        st.caption(f"Current source: {source_label}")

    if uploaded_file is not None:
        frame = load_dataset(uploaded_file.name, uploaded_file.getvalue())
    elif latest_dataset is not None:
        frame = load_dataset(str(latest_dataset))
    else:
        st.error("No local optimisation CSV found. Upload a CSV or Excel extract to continue.")
        return

    filtered_rows = filter_frame(frame)
    item_location_view = build_item_location_view(filtered_rows)
    planogram_item_location_view = build_planogram_item_location_view(filtered_rows)

    if filtered_rows.empty:
        st.warning("No rows match the current filters.")
        return

    overview_tab, opportunities_tab, planograms_tab, layout_tab, stores_tab, raw_tab = st.tabs(
        ["Overview", "Opportunities", "Planograms", "Planogram layout", "Stores", "Raw data"]
    )

    with overview_tab:
        render_overview(item_location_view, planogram_item_location_view, filtered_rows)

    with opportunities_tab:
        render_opportunity_table(item_location_view)

    with planograms_tab:
        render_planogram_summary(planogram_item_location_view)

    with layout_tab:
        render_planogram_layout(filtered_rows)

    with stores_tab:
        render_store_summary(item_location_view)

    with raw_tab:
        st.caption("Raw row-level view. This includes merchandising-style duplicates from the export.")
        render_filterable_table(filtered_rows, height=620, key="raw_data_table")
        st.download_button(
            "Download filtered rows as CSV",
            filtered_rows.to_csv(index=False).encode("utf-8"),
            file_name="space_optimisation_filtered.csv",
            mime="text/csv",
        )


if __name__ == "__main__":
    main()