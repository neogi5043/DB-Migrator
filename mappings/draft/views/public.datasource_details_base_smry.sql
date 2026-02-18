CREATE OR REPLACE VIEW datasource_details_base_smry AS
SELECT 
    ds.datasource_id,
    ds.datasource,
    ds.contains_extract,
    ds.ds_project,
    COUNT(DISTINCT NULLIF(CAST(ds.dashboard_id AS CHAR), '')) AS dashboard_cnt,
    COUNT(DISTINCT NULLIF(CAST(ds.sheet_id AS CHAR), '')) AS sheet_cnt,
    COUNT(DISTINCT NULLIF(CAST(ds.field_id AS CHAR), '')) AS field_cnt,
    COUNT(DISTINCT NULLIF(CAST(ds.workbook_id AS CHAR), '')) AS workbook_cnt,
    COUNT(DISTINCT NULLIF(CAST(ds.table_name AS CHAR), '')) AS table_cnt,
    COUNT(DISTINCT NULLIF(CAST(ds.column_name AS CHAR), '')) AS column_cnt,
    COUNT(DISTINCT NULLIF(CAST(cq.custom_query_id AS CHAR), '')) AS custom_query_cnt
FROM datasource_details_base ds
LEFT JOIN custom_query_details_base cq ON CAST(ds.datasource_id AS CHAR) = CAST(cq.custom_query_id AS CHAR)
WHERE ds.flag = 'Datasource'
GROUP BY ds.datasource_id, ds.datasource, ds.contains_extract, ds.ds_project;