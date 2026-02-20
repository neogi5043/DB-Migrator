CREATE OR REPLACE VIEW workbook_interaction_smry AS
SELECT e.event_id,
       u.workbook,
       u.workbook_id,
       e.event_type,
       e.event_date
FROM usage_statistics_base u
JOIN event_details_base e ON CAST(u.view_id AS CHAR) = CAST(e.item_luid AS CHAR);