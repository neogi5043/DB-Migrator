CREATE OR REPLACE VIEW workbook_details_base_smry AS
WITH ds_totals AS (
    SELECT datasource_details_base.workbook_id,
        COUNT(DISTINCT datasource_details_base.datasource_id) AS datasource_cnt,
        COUNT(DISTINCT datasource_details_base.field_id) AS total_field_cnt,
        COUNT(DISTINCT CONCAT(datasource_details_base.datasource_id, '||', datasource_details_base.column_name)) AS total_column_cnt,
        COUNT(DISTINCT CONCAT(datasource_details_base.datasource_id, '||', datasource_details_base.table_name)) AS total_table_cnt
    FROM datasource_details_base
    WHERE datasource_details_base.flag = 'Workbook'
    GROUP BY datasource_details_base.workbook_id
), dash_used AS (
    SELECT dashboard_details_base.workbook_id,
        dashboard_details_base.workbook,
        COUNT(DISTINCT dashboard_details_base.dashboard_id) AS dashboard_cnt,
        COUNT(DISTINCT dashboard_details_base.sheet_id) AS sheet_cnt,
        COUNT(DISTINCT dashboard_details_base.field_id) AS used_field_cnt,
        COUNT(DISTINCT CONCAT(dashboard_details_base.datasource_id, '||', dashboard_details_base.column_name)) AS used_column_cnt,
        COUNT(DISTINCT CONCAT(dashboard_details_base.datasource_id, '||', dashboard_details_base.table_name)) AS used_table_cnt
    FROM dashboard_details_base
    GROUP BY dashboard_details_base.workbook_id, dashboard_details_base.workbook
), custom_query_counts AS (
    SELECT custom_query_details_base.workbook_id,
        COUNT(DISTINCT custom_query_details_base.custom_query_id) AS custom_query_cnt
    FROM custom_query_details_base
    GROUP BY custom_query_details_base.workbook_id
), view_usg AS (
    SELECT usage_statistics_base.workbook_id,
        SUM(usage_statistics_base.total_views) AS view_cnt
    FROM usage_statistics_base
    GROUP BY usage_statistics_base.workbook_id
)
SELECT du.workbook_id,
    du.workbook,
    du.dashboard_cnt,
    du.sheet_cnt,
    COALESCE(dt.datasource_cnt, 0) AS datasource_cnt,
    COALESCE(dt.total_field_cnt, 0) AS total_field_cnt,
    du.used_field_cnt,
    COALESCE(dt.total_column_cnt, 0) AS total_column_cnt,
    du.used_column_cnt,
    COALESCE(dt.total_table_cnt, 0) AS total_table_cnt,
    du.used_table_cnt,
    COALESCE(cqc.custom_query_cnt, 0) AS custom_query_cnt,
    COALESCE(vu.view_cnt, 0) AS view_cnt
FROM dash_used du
LEFT JOIN ds_totals dt ON du.workbook_id = dt.workbook_id
LEFT JOIN custom_query_counts cqc ON du.workbook_id = cqc.workbook_id
LEFT JOIN view_usg vu ON du.workbook_id = vu.workbook_id;