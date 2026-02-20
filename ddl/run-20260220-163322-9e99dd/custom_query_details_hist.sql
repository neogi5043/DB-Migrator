CREATE TABLE IF NOT EXISTS `Bi_doctor_db`.`custom_query_details_hist` (
    `project_id` LONGTEXT,
    `project` LONGTEXT,
    `workbook_id` LONGTEXT,
    `workbook` LONGTEXT,
    `custom_query_id` LONGTEXT,
    `custom_query` LONGTEXT,
    `query` LONGTEXT,
    `flag` LONGTEXT,
    `file_name` LONGTEXT NOT NULL,
    `load_time` DATETIME(6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
