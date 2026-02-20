CREATE OR REPLACE VIEW datasource_interaction_smry AS
SELECT e.event_id,
       ds.datasource,
       ds.datasource_id,
       e.event_type AS interaction_type,
       e.event_date AS interaction_date
FROM datasource_details_base ds
JOIN event_details_base e ON CAST(ds.datasource_luid AS CHAR) = CAST(e.item_luid AS CHAR)
WHERE ds.flag = 'Datasource';