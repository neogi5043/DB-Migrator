CREATE OR REPLACE VIEW workbook_details_load_log AS
SELECT load_time,
       workbook,
       workbook_id
FROM dashboard_details_hist
GROUP BY load_time, workbook, workbook_id
ORDER BY load_time DESC;