CREATE TABLE IF NOT EXISTS `Bi_doctor_db`.`usage_statistics_base` (
    `project_id` BIGINT NOT NULL,
    `project` VARCHAR(100) NOT NULL,
    `workbook_id` VARCHAR(36) NOT NULL,
    `workbook` VARCHAR(255) NOT NULL,
    `view_id` VARCHAR(36),
    `view` VARCHAR(255),
    `created_at` DATETIME(6),
    `updated_at` DATETIME(6),
    `total_views` INT,
    `file_name` LONGTEXT,
    `load_time` DATETIME(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX `idx_usage_wb` ON `Bi_doctor_db`.`usage_statistics_base` (`workbook_id`);
