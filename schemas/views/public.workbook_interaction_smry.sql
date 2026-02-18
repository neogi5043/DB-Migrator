 SELECT e.event_id,
    u.workbook,
    u.workbook_id,
    e.event_type,
    e.event_date
   FROM (usage_statistics_base u
     JOIN event_details_base e ON (((u.view_id)::text = (e.item_luid)::text)));