CREATE OR REPLACE VIEW datasource_details_load_log AS
SELECT load_time,
       datasource,
       datasource_id
FROM datasource_details_hist
GROUP BY load_time, datasource, datasource_id
ORDER BY load_time DESC;