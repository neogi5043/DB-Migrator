CREATE TABLE IF NOT EXISTS `Bi_doctor_db`.`datasource_details_base` (
    `row_id` BIGINT AUTO_INCREMENT NOT NULL,
    `wb_project_id` BIGINT,
    `wb_project` VARCHAR(100),
    `workbook_id` VARCHAR(36),
    `workbook_luid` VARCHAR(36),
    `workbook` VARCHAR(255),
    `wb_created_date` DATETIME(6),
    `wb_updated_date` DATETIME(6),
    `wb_tags` LONGTEXT,
    `description` LONGTEXT,
    `datasource_id` VARCHAR(36) NOT NULL,
    `datasource` VARCHAR(255) NOT NULL,
    `ds_created_date` DATETIME(6),
    `ds_updated_date` DATETIME(6),
    `ds_project_id` BIGINT,
    `ds_project` VARCHAR(100),
    `ds_tags` LONGTEXT,
    `contains_extract` TINYINT(1) NOT NULL,
    `datasource_type` VARCHAR(50) NOT NULL,
    `field_id` VARCHAR(36) NOT NULL,
    `field_name` VARCHAR(100) NOT NULL,
    `field_type` VARCHAR(50) NOT NULL,
    `formula` LONGTEXT,
    `table_name` VARCHAR(100),
    `column_name` VARCHAR(100),
    `sheet_id` VARCHAR(36),
    `sheet` VARCHAR(255),
    `used_in_sheet` CHAR(1) NOT NULL,
    `dashboard_id` VARCHAR(36),
    `dashboard` VARCHAR(255),
    `custom_query` LONGTEXT,
    `flag` LONGTEXT NOT NULL,
    `file_name` LONGTEXT NOT NULL,
    `load_time` DATETIME(6) NOT NULL,
    `datasource_luid` VARCHAR(36),
    PRIMARY KEY (`row_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX `idx_ds_flag_wb` ON `Bi_doctor_db`.`datasource_details_base` (`workbook_id`, `flag`(64));

CREATE INDEX `idx_ds_flag_wb_ds` ON `Bi_doctor_db`.`datasource_details_base` (`workbook_id`, `datasource_id`, `flag`(64));

CREATE INDEX `idx_ds_flag_wb_ds_col` ON `Bi_doctor_db`.`datasource_details_base` (`workbook_id`, `datasource_id`, `column_name`, `flag`(64));

CREATE INDEX `idx_ds_flag_wb_ds_table` ON `Bi_doctor_db`.`datasource_details_base` (`workbook_id`, `datasource_id`, `table_name`, `flag`(64));

CREATE INDEX `idx_ds_flag_wb_field` ON `Bi_doctor_db`.`datasource_details_base` (`workbook_id`, `field_id`, `flag`(64));
