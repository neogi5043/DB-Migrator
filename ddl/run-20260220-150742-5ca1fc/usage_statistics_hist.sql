CREATE TABLE IF NOT EXISTS `Bi_doctor_db`.`usage_statistics_hist` (
    `project_id` LONGTEXT,
    `project` LONGTEXT,
    `workbook_id` LONGTEXT,
    `workbook` LONGTEXT,
    `view_id` LONGTEXT,
    `view` LONGTEXT,
    `created_at` LONGTEXT,
    `updated_at` LONGTEXT,
    `total_views` LONGTEXT,
    `file_name` LONGTEXT NOT NULL,
    `load_time` DATETIME(6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
