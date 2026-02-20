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

CREATE INDEX `idx_usage_statistics_hist_latest` ON `Bi_doctor_db`.`usage_statistics_hist` (`project_id`(64), `workbook_id`(64), `view_id`(64), `load_time`);

CREATE INDEX `idx_usagestats_hist_load_time` ON `Bi_doctor_db`.`usage_statistics_hist` (`load_time`);
