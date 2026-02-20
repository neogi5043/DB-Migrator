CREATE TABLE IF NOT EXISTS `Bi_doctor_db`.`datasource_details_hist` (
    `wb_project_id` LONGTEXT,
    `wb_project` LONGTEXT,
    `workbook_id` LONGTEXT,
    `workbook_luid` LONGTEXT,
    `workbook` LONGTEXT,
    `wb_created_date` LONGTEXT,
    `wb_updated_date` LONGTEXT,
    `wb_tags` LONGTEXT,
    `description` LONGTEXT,
    `datasource_id` LONGTEXT,
    `datasource` LONGTEXT,
    `ds_created_date` LONGTEXT,
    `ds_updated_date` LONGTEXT,
    `ds_project_id` LONGTEXT,
    `ds_project` LONGTEXT,
    `ds_tags` LONGTEXT,
    `contains_extract` LONGTEXT,
    `datasource_type` LONGTEXT,
    `field_id` LONGTEXT,
    `field_name` LONGTEXT,
    `field_type` LONGTEXT,
    `formula` LONGTEXT,
    `table` LONGTEXT,
    `column` LONGTEXT,
    `sheet_id` LONGTEXT,
    `sheet` LONGTEXT,
    `used_in_sheet` LONGTEXT,
    `dashboard_id` LONGTEXT,
    `dashboard` LONGTEXT,
    `custom_query` LONGTEXT,
    `flag` LONGTEXT,
    `file_name` LONGTEXT NOT NULL,
    `load_time` DATETIME(6) NOT NULL,
    `datasource_luid` LONGTEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX `idx_datasource_details_hist_latest` ON `Bi_doctor_db`.`datasource_details_hist` (`wb_project_id`(64), `workbook_id`(64), `datasource_id`(64), `ds_project_id`(64), `field_id`(64), `sheet_id`(64), `dashboard_id`(64), `load_time`);

CREATE INDEX `idx_datasource_hist_load_time` ON `Bi_doctor_db`.`datasource_details_hist` (`load_time`);

CREATE INDEX `idx_ds_hist_fast` ON `Bi_doctor_db`.`datasource_details_hist` (`wb_project_id`(64), `workbook_id`(64), `datasource_id`(64), `ds_project_id`(64), `field_id`(64), `sheet_id`(64), `dashboard_id`(64), `load_time`);

CREATE INDEX `idx_hist_load_time` ON `Bi_doctor_db`.`datasource_details_hist` (`load_time`);
