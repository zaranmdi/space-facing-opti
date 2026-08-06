-- WITH params AS (
--     SELECT
--         DATE '2026-07-30' AS sales_end_date,
--         DATEADD(WEEK, -52, DATE '2026-07-30') AS sales_start_date
-- ),

WITH params AS (
    SELECT
        DATEADD(day, -1, CURRENT_DATE()) AS sales_end_date,
        DATEADD(
            week,
            -52,
            DATEADD(day, -1, CURRENT_DATE())
        ) AS sales_start_date
),

/* ---------------------------------------------------------
   Live planograms only
--------------------------------------------------------- */
live_planograms AS (
    SELECT
        DW_PLANOGRAM_ID,
        MAX(PLANOGRAM_ID) AS PLANOGRAM_ID,
        MAX(PLANOGRAM_NAME) AS PLANOGRAM_NAME,
        MAX(PLANOGRAM_DEPARTMENT_NAME) AS PLANOGRAM_DEPARTMENT_NAME
    FROM BDWPRD_CDS.SPACE_PLANNING.PLANOGRAM_DIM
    WHERE PLANOGRAM_STATUS_CODE = 'LIVE'
      AND PLANOGRAM_DEPARTMENT_NAME IN (
            -- 'KITCHEN BATH & SPECIAL ORDERS',
            '300 KITCHEN AND APPLIANCES'
      )
      AND PLANOGRAM_EFFECTIVE_TO_DATE is null -- check this with PK and Andrew
    GROUP BY
        DW_PLANOGRAM_ID
),

/* ---------------------------------------------------------
   Item grade from BlueYonder product table
--------------------------------------------------------- */
item_grade AS (
    SELECT
        COUNTRY_CODE,
        item_number,
        item_grade,
        facings,
        hfacings,
        vfacings
    FROM (
        SELECT
            pr.DESC1 AS COUNTRY_CODE,
            REPLACE(REPLACE(pr.ID, '-AU', ''), '-NZ', '') AS item_number,
            pr.DESC8 AS item_grade,
            ps.facings,
            ps.hfacings,
            ps.vfacings,
            ROW_NUMBER() OVER (
                PARTITION BY
                    pr.DESC1,
                    REPLACE(REPLACE(pr.ID, '-AU', ''), '-NZ', '')
                ORDER BY pr.DW_STRT_TS DESC
            ) AS rn
        FROM BDWPRD_SRCI.BLUEYONDER_CKB.IX_SPC_PRODUCT pr
        LEFT JOIN (
            SELECT
                dbparentproductkey,
                facings,
                hfacings,
                vfacings
            FROM BDWPRD_SRCI.BLUEYONDER_CKB.IX_SPC_POSITION
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY DBKey
                ORDER BY DW_STRT_TS DESC
            ) = 1
            AND DW_REC_DEL_IND = FALSE
        ) ps
            ON pr.DBKey = ps.dbparentproductkey
        WHERE pr.DW_REC_DEL_IND = FALSE
    )
    WHERE rn = 1
),

/* ---------------------------------------------------------
   Item-location ranging stats
   Current status resolved from ITEM_STATUS SCD2 table.
--------------------------------------------------------- */
ranging_stats AS (
    SELECT
        agg.DW_ITEM_ID,
        agg.DW_LOCATION_ID,
        agg.first_sales_date,
        agg.earliest_inventory_stock_movement_date,
        ist.DW_ITEM_STATUS_ID AS current_dw_item_status_id,
        isdim.ITEM_STATUS_CODE AS current_item_status_code
    FROM (
        SELECT
            DW_ITEM_ID,
            DW_LOCATION_ID,
            MIN(CAST(FIRST_SALE_DATE AS DATE)) AS first_sales_date,
            MIN(CAST(EARLIEST_INVENTORY_STOCK_MOVEMENT_DATE AS DATE))
                AS earliest_inventory_stock_movement_date
        FROM BDWPRD_CDS.MERCHANDISING.ITEM_LOCATION_RANGING_STATS_FCT
        GROUP BY DW_ITEM_ID, DW_LOCATION_ID
    ) agg
    LEFT JOIN BDWPRD_IDS.INVENTORY.ITEM_LOCATION_STATUS ist
        ON  ist.DW_ITEM_ID     = agg.DW_ITEM_ID
        AND ist.DW_LOCATION_ID = agg.DW_LOCATION_ID
        AND ist.DW_END_TS      = '9999-12-31 23:59:59.999999999'
        AND ist.DW_REC_DEL_IND = FALSE
    LEFT JOIN BDWPRD_CDS.COMMON.ITEM_STATUS_DIM isdim
        ON isdim.DW_ITEM_STATUS_ID = ist.DW_ITEM_STATUS_ID
),

/* ---------------------------------------------------------
   Count number of live planograms per item-location
--------------------------------------------------------- */
planogram_counts AS (
    SELECT
        ilp.DW_ITEM_ID,
        ilp.DW_LOCATION_ID,
        COUNT(DISTINCT ilp.DW_PLANOGRAM_ID) AS planogram_cnt
    FROM BDWPRD_CDS.SPACE_PLANNING.PLANOGRAM_ITEM_LOCATION_BRIDGE ilp

    JOIN live_planograms pg
        ON ilp.DW_PLANOGRAM_ID = pg.DW_PLANOGRAM_ID

    GROUP BY
        ilp.DW_ITEM_ID,
        ilp.DW_LOCATION_ID
),

/* ---------------------------------------------------------
   Daily item-location sales
   Replaces SALES_ITEM_LOCATION_WEEK_FCT.
--------------------------------------------------------- */
item_location_sale AS (
    SELECT
        CAST(s.PERIOD_DATE AS DATE) AS period_date,
        s.DW_ITEM_ID AS item_id,
        s.DW_LOCATION_ID AS loc_id,

        SUM(COALESCE(s.SALES_QUANTITY, 0)) AS daily_sales_quantity,

        SUM(
            CASE WHEN s.SALES_CHANNEL_CODE = 'InStore'
                 THEN COALESCE(s.SALES_QUANTITY,0)
                 ELSE 0
            END
        ) AS instore_sales_qty,

        SUM(
            CASE WHEN s.SALES_CHANNEL_CODE = 'Online'
                 THEN COALESCE(s.SALES_QUANTITY,0)
                 ELSE 0
            END
        ) AS online_sales_qty,

        SUM(
            CASE WHEN s.SALES_CHANNEL_CODE = '.Unk'
                 THEN COALESCE(s.SALES_QUANTITY,0)
                 ELSE 0
            END
        ) AS unk_sales_qty,

        SUM(COALESCE(s.TOTAL_SALES_EXCLUDE_GST_AMOUNT, 0))
            AS daily_sales_excluding_gst_amount

    FROM BDWPRD_CDS.SALES.SALES_ITEM_LOCATION_DAY_FCT s

    CROSS JOIN params p

    JOIN planogram_counts pc
        ON s.DW_ITEM_ID = pc.DW_ITEM_ID
       AND s.DW_LOCATION_ID = pc.DW_LOCATION_ID

    WHERE CAST(s.PERIOD_DATE AS DATE) > p.sales_start_date
      AND CAST(s.PERIOD_DATE AS DATE) <= p.sales_end_date

    GROUP BY
        CAST(s.PERIOD_DATE AS DATE),
        s.DW_ITEM_ID,
        s.DW_LOCATION_ID
),

/* ---------------------------------------------------------
   All item-location statuses overlapping the 52-week window
   This is descriptive only. It is NOT used to filter rows.
--------------------------------------------------------- */
item_status_rows_52 AS (
    SELECT
        pc.DW_ITEM_ID,
        pc.DW_LOCATION_ID,

        COALESCE(ils_status.ITEM_STATUS_CODE, 'UNKNOWN') AS item_status_code,

        MIN(
            GREATEST(
                CAST(ils.DW_STRT_TS AS DATE),
                p.sales_start_date
            )
        ) AS status_start_in_window

    FROM planogram_counts pc

    CROSS JOIN params p

    JOIN BDWPRD_IDS.INVENTORY.ITEM_LOCATION_STATUS ils
        ON pc.DW_ITEM_ID = ils.DW_ITEM_ID
       AND pc.DW_LOCATION_ID = ils.DW_LOCATION_ID
       AND CAST(ils.DW_STRT_TS AS DATE) <= p.sales_end_date
       AND COALESCE(CAST(ils.DW_END_TS AS DATE), DATE '9999-12-31') > p.sales_start_date
       AND ils.DW_REC_DEL_IND = FALSE

    LEFT JOIN BDWPRD_CDS.COMMON.ITEM_STATUS_DIM ils_status
        ON ils_status.DW_ITEM_STATUS_ID = ils.DW_ITEM_STATUS_ID

    GROUP BY
        pc.DW_ITEM_ID,
        pc.DW_LOCATION_ID,
        COALESCE(ils_status.ITEM_STATUS_CODE, 'UNKNOWN')
),

/* ---------------------------------------------------------
   Status list per item-location across the 52-week window
--------------------------------------------------------- */
item_status_52 AS (
    SELECT
        DW_ITEM_ID,
        DW_LOCATION_ID,

        LISTAGG(item_status_code, ', ')
            WITHIN GROUP (
                ORDER BY status_start_in_window, item_status_code
            ) AS item_status_code_list,

        COUNT(DISTINCT item_status_code) AS item_status_code_count

    FROM item_status_rows_52

    GROUP BY
        DW_ITEM_ID,
        DW_LOCATION_ID
),

/* ---------------------------------------------------------
   52-week actual sales from daily sales table
--------------------------------------------------------- */
actual_sales_52 AS (
    SELECT
        smt.item_id AS DW_ITEM_ID,
        smt.loc_id AS DW_LOCATION_ID,
        p.sales_start_date,
        p.sales_end_date,

        SUM(COALESCE(smt.daily_sales_quantity, 0))
            AS actual_sales_quantity,

        SUM(COALESCE(smt.instore_sales_qty, 0))
            AS instore_sales_qty_52w,

        SUM(COALESCE(smt.online_sales_qty, 0))
            AS online_sales_qty_52w,

        SUM(COALESCE(smt.unk_sales_qty, 0))
            AS unk_sales_qty_52w,

        SUM(COALESCE(smt.daily_sales_excluding_gst_amount, 0))
            AS actual_sales_excluding_gst_52w

    FROM item_location_sale smt

    CROSS JOIN params p

    GROUP BY
        smt.item_id,
        smt.loc_id,
        p.sales_start_date,
        p.sales_end_date
),



/* ---------------------------------------------------------
   Sales universe starts from planogram item-locations
   so rows are not lost only because there are no sales.
--------------------------------------------------------- */
sales_universe AS (
    SELECT
        pc.DW_ITEM_ID,
        pc.DW_LOCATION_ID,
        p.sales_start_date,
        p.sales_end_date,
        pc.planogram_cnt
    FROM planogram_counts pc
    CROSS JOIN params p
),

/* ---------------------------------------------------------
   Combine actual sales, planogram count, ranging stats,
   52-week status list, and current item status.
--------------------------------------------------------- */
sales_52_base AS (
    SELECT
        su.DW_ITEM_ID,
        su.DW_LOCATION_ID,
        su.sales_start_date,
        su.sales_end_date,

        r.first_sales_date,
        r.earliest_inventory_stock_movement_date,

        r.current_dw_item_status_id,
        r.current_item_status_code,

        st.item_status_code_list,
        st.item_status_code_count,

        GREATEST(
            COALESCE(
                r.first_sales_date,
                r.earliest_inventory_stock_movement_date,
                su.sales_start_date
            ),
            su.sales_start_date
        ) AS active_start_date,

        COALESCE(a.actual_sales_quantity, 0) AS actual_sales_quantity,
        COALESCE(a.instore_sales_qty_52w, 0) AS instore_sales_qty_52w,
        COALESCE(a.online_sales_qty_52w, 0) AS online_sales_qty_52w,
        COALESCE(a.unk_sales_qty_52w, 0) AS unk_sales_qty_52w,
        COALESCE(a.actual_sales_excluding_gst_52w, 0) AS actual_sales_excluding_gst_52w,

        COALESCE(su.planogram_cnt, 1) AS planogram_cnt

    FROM sales_universe su

    LEFT JOIN actual_sales_52 a
        ON su.DW_ITEM_ID = a.DW_ITEM_ID
       AND su.DW_LOCATION_ID = a.DW_LOCATION_ID
       AND su.sales_start_date = a.sales_start_date
       AND su.sales_end_date = a.sales_end_date

    LEFT JOIN ranging_stats r
        ON su.DW_ITEM_ID = r.DW_ITEM_ID
       AND su.DW_LOCATION_ID = r.DW_LOCATION_ID

    LEFT JOIN item_status_52 st
        ON su.DW_ITEM_ID = st.DW_ITEM_ID
       AND su.DW_LOCATION_ID = st.DW_LOCATION_ID
),

/* ---------------------------------------------------------
   Calculate active weeks and missing weeks
--------------------------------------------------------- */
sales_52_weeks AS (
    SELECT
        *,

        LEAST(
            GREATEST(
                DATEDIFF(
                    'day',
                    active_start_date,
                    sales_end_date
                ) / 7.0,
                1
            ),
            52
        ) AS active_weeks,

        GREATEST(
            52 - LEAST(
                GREATEST(
                    DATEDIFF(
                        'day',
                        active_start_date,
                        sales_end_date
                    ) / 7.0,
                    1
                ),
                52
            ),
            0
        ) AS missing_weeks

    FROM sales_52_base
),

/* ---------------------------------------------------------
   Latest weekly forecast records
   Forecast table remains weekly.
--------------------------------------------------------- */
forecast_weekly_latest AS (
    SELECT
        f.DW_ITEM_ID,
        f.DW_LOCATION_ID,
        CAST(f.PERIOD_DATE AS DATE) AS forecast_period_date,

        COALESCE( 
            f.FORECAST_TOTAL_SALES_QUANTITY,
            f.CONSTRAINED_FORECAST_TOTAL_SALES_QUANTITY,
            f.FORECAST_BASE_SALES_QUANTITY,
            0
        ) AS forecast_sales_quantity,

        COALESCE(
            f.DERIVED_FORECAST_TOTAL_SALES_AMOUNT,
            f.DERIVED_CONSTRAINED_FORECAST_TOTAL_SALES_AMOUNT,
            f.DERIVED_FORECAST_BASE_SALES_AMOUNT,
            0
        ) AS forecast_sales_amount,

        ROW_NUMBER() OVER (
            PARTITION BY
                f.DW_ITEM_ID,
                f.DW_LOCATION_ID,
                f.PERIOD_DATE
            ORDER BY
                f.FORECAST_DATE DESC,
                f.DW_PROCESS_TS DESC
        ) AS rn

    FROM BDWPRD_CDS.SALES.FORECASTED_SALES_ITEM_LOCATION_WEEK_FCT f

    CROSS JOIN params p

    JOIN planogram_counts pc
        ON f.DW_ITEM_ID = pc.DW_ITEM_ID
       AND f.DW_LOCATION_ID = pc.DW_LOCATION_ID

    WHERE CAST(f.PERIOD_DATE AS DATE) > p.sales_end_date
      AND CAST(f.PERIOD_DATE AS DATE) <= DATEADD(WEEK, 52, p.sales_end_date)
),

/* ---------------------------------------------------------
   Forecast only for missing weeks
--------------------------------------------------------- */
forecast_missing_sales AS (
    SELECT
        sw.DW_ITEM_ID,
        sw.DW_LOCATION_ID,
        sw.sales_start_date,
        sw.sales_end_date,

        SUM(
            CASE
                WHEN sw.missing_weeks > 0
                 AND f.rn = 1
                 AND f.forecast_period_date > sw.sales_end_date
                 AND f.forecast_period_date <= DATEADD(WEEK, CEIL(sw.missing_weeks), sw.sales_end_date)
                THEN COALESCE(f.forecast_sales_quantity, 0)
                ELSE 0
            END
        ) AS forecasted_sales_quantity,

        SUM(
            CASE
                WHEN sw.missing_weeks > 0
                 AND f.rn = 1
                 AND f.forecast_period_date > sw.sales_end_date
                 AND f.forecast_period_date <= DATEADD(WEEK, CEIL(sw.missing_weeks), sw.sales_end_date)
                THEN COALESCE(f.forecast_sales_amount, 0)
                ELSE 0
            END
        ) AS forecasted_sales_excluding_gst

    FROM sales_52_weeks sw

    LEFT JOIN forecast_weekly_latest f
        ON sw.DW_ITEM_ID = f.DW_ITEM_ID
       AND sw.DW_LOCATION_ID = f.DW_LOCATION_ID

    GROUP BY
        sw.DW_ITEM_ID,
        sw.DW_LOCATION_ID,
        sw.sales_start_date,
        sw.sales_end_date
),

/* ---------------------------------------------------------
   Calculate forecast-adjusted 52-week sales and UnitsPSPW52
--------------------------------------------------------- */
sales_52 AS (
    SELECT
        sw.DW_ITEM_ID,
        sw.DW_LOCATION_ID,
        sw.sales_start_date,
        sw.sales_end_date,

        sw.first_sales_date,
        sw.earliest_inventory_stock_movement_date,

        sw.current_dw_item_status_id,
        sw.current_item_status_code,

        sw.item_status_code_list,
        sw.item_status_code_count,

        sw.active_start_date,
        sw.active_weeks,
        sw.missing_weeks,

        sw.planogram_cnt,

        sw.actual_sales_quantity,
        sw.actual_sales_excluding_gst_52w,

        sw.instore_sales_qty_52w,
        sw.online_sales_qty_52w,
        sw.unk_sales_qty_52w,

        COALESCE(fms.forecasted_sales_quantity, 0) AS forecasted_sales_quantity,
        COALESCE(fms.forecasted_sales_excluding_gst, 0) AS forecasted_sales_excluding_gst,

        CASE
            WHEN sw.active_weeks < 52
            THEN sw.actual_sales_quantity + COALESCE(fms.forecasted_sales_quantity, 0)
            ELSE sw.actual_sales_quantity
        END AS forecast_adjusted_qty_52w,

        CASE
            WHEN sw.active_weeks < 52
            THEN sw.actual_sales_excluding_gst_52w + COALESCE(fms.forecasted_sales_excluding_gst, 0)
            ELSE sw.actual_sales_excluding_gst_52w
        END AS forecast_adjusted_sales_amount_52w,

        CASE
            WHEN sw.active_weeks < 52
            THEN 1
            ELSE 0
        END AS used_forecast_flag,

        CASE
            WHEN sw.active_weeks < 52
            THEN 'ACTUAL + FORECAST'
            ELSE 'ACTUAL 52W'
        END AS sales_basis,

        (
            CASE
                WHEN sw.active_weeks < 52
                THEN sw.actual_sales_quantity + COALESCE(fms.forecasted_sales_quantity, 0)
                ELSE sw.actual_sales_quantity
            END
        )
            / NULLIF(sw.planogram_cnt, 0)
            / 52.0 AS UnitsPSPW52,

        (
            CASE
                WHEN sw.active_weeks < 52
                THEN sw.actual_sales_excluding_gst_52w + COALESCE(fms.forecasted_sales_excluding_gst, 0)
                ELSE sw.actual_sales_excluding_gst_52w
            END
        )
            / NULLIF(sw.planogram_cnt, 0) AS forecast_adjusted_sales_excluding_gst

    FROM sales_52_weeks sw

    LEFT JOIN forecast_missing_sales fms
        ON sw.DW_ITEM_ID = fms.DW_ITEM_ID
       AND sw.DW_LOCATION_ID = fms.DW_LOCATION_ID
       AND sw.sales_start_date = fms.sales_start_date
       AND sw.sales_end_date = fms.sales_end_date
),

/* ---------------------------------------------------------
   Main base table
--------------------------------------------------------- */
base AS (
    SELECT DISTINCT
        p.sales_start_date,
        p.sales_end_date,

        pp.DW_PLANOGRAM_ID,
        pg.PLANOGRAM_ID,
        pg.PLANOGRAM_NAME,
        pg.PLANOGRAM_DEPARTMENT_NAME,

        ilp.DW_LOCATION_ID,
        l.LOCATION_NAME,
        l.LOCATION_CODE,
        l.IS_CLOSED,
        l.location_type_code,

        pp.DW_ITEM_ID,
        pp.COUNTRY_CODE,
        ms.MERCHANDISING_STYLE_CODE,

        pp.CAPACITY,
        ii.ITEM_NUMBER,
        ii.ITEM_DESCRIPTION,

        ig.item_grade,
        ig.facings,
        ig.hfacings,
        ig.vfacings,

        i.PURCHASING_UOM_RATE,
        pp.CAPACITY / NULLIF(i.PURCHASING_UOM_RATE, 0) AS pack_on_show

    FROM BDWPRD_IDS.SPACE_PLANNING.PLANOGRAM_PERFORMANCE pp

    CROSS JOIN params p

    JOIN BDWPRD_CDS.ITEM.ITEM_DIM ii
        ON pp.DW_ITEM_ID = ii.DW_ITEM_ID

    LEFT JOIN item_grade ig
        ON TO_VARCHAR(ii.ITEM_NUMBER) = TO_VARCHAR(ig.item_number)
       AND pp.COUNTRY_CODE = ig.COUNTRY_CODE

    JOIN BDWPRD_CDS.SUPPLIER.ITEM_SUPPLIER_FCT i
        ON pp.DW_ITEM_ID = i.DW_ITEM_ID
       AND i.PRIMARY_IND = TRUE

    JOIN live_planograms pg
        ON pp.DW_PLANOGRAM_ID = pg.DW_PLANOGRAM_ID

    JOIN BDWPRD_CDS.SPACE_PLANNING.PLANOGRAM_ITEM_LOCATION_BRIDGE ilp
        ON pp.DW_PLANOGRAM_ID = ilp.DW_PLANOGRAM_ID
       AND pp.DW_ITEM_ID = ilp.DW_ITEM_ID

    JOIN BDWPRD_CDS.LOCATION.LOCATION_DIM l
        ON ilp.DW_LOCATION_ID = l.DW_LOCATION_ID

    LEFT JOIN BDWPRD_IDS.SPACE_PLANNING.PLANOGRAM_PRODUCT_PLACEMENT ppp
        ON pp.DW_ITEM_ID = ppp.DW_ITEM_ID
       AND pp.DW_PLANOGRAM_ID = ppp.DW_PLANOGRAM_ID
       AND ppp.DW_END_TS = '9999-12-31 23:59:59.999999999'
       AND ppp.DW_REC_DEL_IND = FALSE

    LEFT JOIN BDWPRD_IDS.SPACE_PLANNING.MERCHANDISING_STYLE ms
        ON ppp.DW_MERCHANDISING_STYLE_ID = ms.DW_MERCHANDISING_STYLE_ID
       AND ms.DW_END_TS = '9999-12-31 23:59:59.999999999'
       AND ms.DW_REC_DEL_IND = FALSE

    WHERE pp.DW_END_TS = '9999-12-31 23:59:59.999999999'
      AND pp.DW_REC_DEL_IND = FALSE
      AND pp.CAPACITY > 0

      -- Keep commented unless you want to exclude displays:
      -- AND COALESCE(ms.MERCHANDISING_STYLE_CODE, '') <> 'Display'
),

/* ---------------------------------------------------------
   Metrics and flags
--------------------------------------------------------- */
metrics AS (
    SELECT
        b.*,

        s.first_sales_date,
        s.earliest_inventory_stock_movement_date,

        s.current_dw_item_status_id,
        s.current_item_status_code,

        s.item_status_code_list,
        s.item_status_code_count,

        s.active_start_date,
        s.active_weeks,
        s.missing_weeks,

        s.planogram_cnt,

        s.actual_sales_quantity,
        s.actual_sales_excluding_gst_52w,

        s.instore_sales_qty_52w,
        s.online_sales_qty_52w,
        s.unk_sales_qty_52w,

        s.forecasted_sales_quantity,
        s.forecasted_sales_excluding_gst,

        s.forecast_adjusted_qty_52w,
        s.forecast_adjusted_sales_amount_52w,
        s.forecast_adjusted_sales_excluding_gst,

        s.used_forecast_flag,
        s.sales_basis,

        s.UnitsPSPW52,

        b.CAPACITY / NULLIF(s.UnitsPSPW52, 0) AS WOS,

        CASE
            WHEN b.CAPACITY / NULLIF(s.UnitsPSPW52, 0) < 3
            THEN 1 ELSE 0
        END AS low_wos_flag,

        CASE
            WHEN b.pack_on_show < 1.25
            THEN 1 ELSE 0
        END AS low_pack_on_show_flag,

        CASE
            WHEN b.CAPACITY / NULLIF(s.UnitsPSPW52, 0) < 3
              OR b.pack_on_show < 1.25
            THEN 1 ELSE 0
        END AS needs_more_space_flag,

        CASE
            WHEN b.CAPACITY / NULLIF(s.UnitsPSPW52, 0) >= 8
             AND COALESCE(s.UnitsPSPW52, 0) > 0
             AND b.pack_on_show >= 2
            THEN 1 ELSE 0
        END AS possible_space_donor_flag,

        CASE
            WHEN COALESCE(s.UnitsPSPW52,0) = 0
                THEN 1
                ELSE 0
            END AS no_sales_flag,

        COALESCE(s.UnitsPSPW52, 0) / NULLIF(b.CAPACITY, 0) AS sales_per_capacity_unit

    FROM base b

    LEFT JOIN sales_52 s
        ON b.DW_ITEM_ID = s.DW_ITEM_ID
       AND b.DW_LOCATION_ID = s.DW_LOCATION_ID
       AND b.sales_start_date = s.sales_start_date
       AND b.sales_end_date = s.sales_end_date
),

/* ---------------------------------------------------------
   Apply final eligibility filters before ranking
   No item-status-code filter is applied here.
--------------------------------------------------------- */
eligible_metrics AS (
    SELECT *
    FROM metrics
    WHERE IS_CLOSED = FALSE
      AND COALESCE(location_type_code, '') <> 'TD'
),

/* ---------------------------------------------------------
   Rank items within planogram-location
--------------------------------------------------------- */
ranked AS (
    SELECT
        *,
        PERCENT_RANK() OVER (
            PARTITION BY DW_PLANOGRAM_ID, DW_LOCATION_ID
            ORDER BY sales_per_capacity_unit
        ) AS productivity_rank,

        PERCENT_RANK() OVER (
            PARTITION BY DW_PLANOGRAM_ID, DW_LOCATION_ID
            ORDER BY WOS
        ) AS wos_rank
    FROM eligible_metrics
),

final AS (
    SELECT DISTINCT
        sales_start_date,
        sales_end_date,

        first_sales_date,
        earliest_inventory_stock_movement_date,

        TO_VARCHAR(current_dw_item_status_id, 'HEX') as current_dw_item_status_id,
        current_item_status_code,

        item_status_code_list,
        item_status_code_count,

        active_start_date,
        active_weeks,
        missing_weeks,

        TO_VARCHAR(DW_PLANOGRAM_ID, 'HEX') as DW_PLANOGRAM_ID,
        PLANOGRAM_ID,
        PLANOGRAM_NAME,
        PLANOGRAM_DEPARTMENT_NAME,

        TO_VARCHAR(DW_LOCATION_ID, 'HEX') as DW_LOCATION_ID,
        LOCATION_NAME,
        LOCATION_CODE,
        IS_CLOSED,
        location_type_code,

        TO_VARCHAR(DW_ITEM_ID, 'HEX') as DW_ITEM_ID,
        ITEM_NUMBER,
        ITEM_DESCRIPTION,
        item_grade,
        facings,
        hfacings,
        vfacings,
        MERCHANDISING_STYLE_CODE,

        CAPACITY,
        PURCHASING_UOM_RATE,
        pack_on_show,

        planogram_cnt,

        actual_sales_quantity,
        actual_sales_excluding_gst_52w,

        instore_sales_qty_52w,
        online_sales_qty_52w,
        unk_sales_qty_52w,

        forecasted_sales_quantity,
        forecasted_sales_excluding_gst,

        forecast_adjusted_qty_52w,
        forecast_adjusted_sales_amount_52w,
        forecast_adjusted_sales_excluding_gst,

        used_forecast_flag,
        sales_basis,

        UnitsPSPW52,
        WOS,
        sales_per_capacity_unit,
        productivity_rank,
        wos_rank,

        low_wos_flag,
        low_pack_on_show_flag,
        needs_more_space_flag,
        possible_space_donor_flag,

        CASE
            WHEN COALESCE(UnitsPSPW52,0) = 0
            THEN 'NO SALES - REVIEW SPACE'

            WHEN needs_more_space_flag = 1
                AND productivity_rank >= 0.70
            THEN 'HIGH PRIORITY - ADD SPACE'

            WHEN needs_more_space_flag = 1
            THEN 'ADD SPACE / REVIEW'

            WHEN possible_space_donor_flag = 1
                AND productivity_rank <= 0.30
            THEN 'SPACE DONOR - REDUCE SPACE'

            WHEN WOS >= 12
            THEN 'HIGH WOS - REVIEW OVERSPACE'

            ELSE 'OK'
        END AS space_optimization_opportunity

    FROM ranked
)

SELECT *
FROM final
ORDER BY
    DW_PLANOGRAM_ID,
    DW_LOCATION_ID,
    CASE
        WHEN space_optimization_opportunity = 'HIGH PRIORITY - ADD SPACE' THEN 1
        WHEN space_optimization_opportunity = 'ADD SPACE / REVIEW' THEN 2
        WHEN space_optimization_opportunity = 'SPACE DONOR - REDUCE SPACE' THEN 3
        ELSE 4
    END,
    sales_per_capacity_unit DESC;