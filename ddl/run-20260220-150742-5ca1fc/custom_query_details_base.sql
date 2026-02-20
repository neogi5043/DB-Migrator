CREATE TABLE IF NOT EXISTS `Bi_doctor_db`.`custom_query_details_base` (
    `project_id` BIGINT NOT NULL,
    `project` VARCHAR(100) NOT NULL,
    `workbook_id` VARCHAR(36) NOT NULL,
    `workbook` VARCHAR(255) NOT NULL,
    `custom_query_id` VARCHAR(36),
    `custom_query` LONGTEXT,
    `query` LONGTEXT,
    `flag` LONGTEXT NOT NULL,
    `file_name` LONGTEXT,
    `load_time` DATETIME(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
