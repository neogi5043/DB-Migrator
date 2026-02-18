 SELECT ds.datasource_id,
    ds.datasource,
    ds.contains_extract,
    ds.ds_project,
    count(DISTINCT NULLIF((ds.dashboard_id)::text, ''::text)) AS dashboard_cnt,
    count(DISTINCT NULLIF((ds.sheet_id)::text, ''::text)) AS sheet_cnt,
    count(DISTINCT NULLIF((ds.field_id)::text, ''::text)) AS field_cnt,
    count(DISTINCT NULLIF((ds.workbook_id)::text, ''::text)) AS workbook_cnt,
    count(DISTINCT NULLIF((ds.table_name)::text, ''::text)) AS table_cnt,
    count(DISTINCT NULLIF((ds.column_name)::text, ''::text)) AS column_cnt,
    count(DISTINCT NULLIF((cq.custom_query_id)::text, ''::text)) AS custom_query_cnt
   FROM (datasource_details_base ds
     LEFT JOIN custom_query_details_base cq ON (((ds.datasource_id)::text = (cq.custom_query_id)::text)))
  WHERE (ds.flag = 'Datasource'::text)
  GROUP BY ds.datasource_id, ds.datasource, ds.contains_extract, ds.ds_project;