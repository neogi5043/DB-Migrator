CREATE TABLE IF NOT EXISTS `Bi_doctor_db`.`dashboard_details_hist` (
    `project_id` LONGTEXT,
    `project` LONGTEXT,
    `workbook_id` LONGTEXT,
    `workbook` LONGTEXT,
    `workbook_owner_id` LONGTEXT,
    `workbook_owner_username` LONGTEXT,
    `dashboard_id` LONGTEXT,
    `dashboard` LONGTEXT,
    `sheet_id` LONGTEXT,
    `sheet` LONGTEXT,
    `field_id` LONGTEXT,
    `field` LONGTEXT,
    `field_type` LONGTEXT,
    `datasource_id` LONGTEXT,
    `datasource` LONGTEXT,
    `table_name` LONGTEXT,
    `column_name` LONGTEXT,
    `formula` LONGTEXT,
    `file_name` LONGTEXT NOT NULL,
    `load_time` DATETIME(6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX `idx_dashboard_details_hist_latest` ON `Bi_doctor_db`.`dashboard_details_hist` (`project_id`(64), `workbook_id`(64), `dashboard_id`(64), `sheet_id`(64), `field_id`(64), `datasource_id`(64), `load_time`);

CREATE INDEX `idx_dashboard_hist_load_time` ON `Bi_doctor_db`.`dashboard_details_hist` (`load_time`);
