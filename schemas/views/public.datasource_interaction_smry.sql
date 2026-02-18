 SELECT e.event_id,
    ds.datasource,
    ds.datasource_id,
    e.event_type AS interaction_type,
    e.event_date AS interaction_date
   FROM (datasource_details_base ds
     JOIN event_details_base e ON (((ds.datasource_luid)::text = (e.item_luid)::text)))
  WHERE (ds.flag = 'Datasource'::text);