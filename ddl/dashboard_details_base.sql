CREATE TABLE IF NOT EXISTS `Bi_doctor_db`.`dashboard_details_base` (
    `row_id` BIGINT NOT NULL,
    `project_id` BIGINT NOT NULL,
    `project` VARCHAR(50) NOT NULL,
    `workbook_id` VARCHAR(36) NOT NULL,
    `workbook` VARCHAR(250) NOT NULL,
    `workbook_owner_id` VARCHAR(36),
    `workbook_owner_username` VARCHAR(255),
    `dashboard_id` VARCHAR(36),
    `dashboard` VARCHAR(255),
    `sheet_id` VARCHAR(36),
    `sheet` VARCHAR(255),
    `field_id` VARCHAR(36),
    `field` VARCHAR(255),
    `field_type` VARCHAR(50),
    `datasource_id` VARCHAR(36),
    `datasource` VARCHAR(255),
    `table_name` VARCHAR(100),
    `column_name` VARCHAR(100),
    `formula` LONGTEXT,
    `file_name` VARCHAR(100),
    `load_time` DATETIME(6),
    PRIMARY KEY (`row_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX `idx_dash_wb` ON `Bi_doctor_db`.`dashboard_details_base` (`workbook_id`);

CREATE INDEX `idx_dash_wb_ds` ON `Bi_doctor_db`.`dashboard_details_base` (`workbook_id`, `datasource_id`);

CREATE INDEX `idx_dash_wb_ds_col` ON `Bi_doctor_db`.`dashboard_details_base` (`workbook_id`, `datasource_id`, `column_name`);

CREATE INDEX `idx_dash_wb_ds_table` ON `Bi_doctor_db`.`dashboard_details_base` (`workbook_id`, `datasource_id`, `table_name`);

CREATE INDEX `idx_dash_wb_field` ON `Bi_doctor_db`.`dashboard_details_base` (`workbook_id`, `field_id`);
