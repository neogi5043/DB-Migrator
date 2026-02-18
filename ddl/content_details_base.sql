CREATE TABLE IF NOT EXISTS `Bi_doctor_db`.`content_details_base` (
    `item_luid` VARCHAR(36) NOT NULL,
    `item_id` VARCHAR(36),
    `item_name` VARCHAR(100),
    `item_type` VARCHAR(20),
    `item_parent_project_name` VARCHAR(100),
    `item_parent_project_id` VARCHAR(36),
    `top_parent_project_name` VARCHAR(100),
    `last_accessed_at` DATETIME(6),
    `owner_email` VARCHAR(100),
    `item_hyperlink` LONGTEXT,
    `total_size_mb` DECIMAL(12,6),
    `load_time` DATETIME(6),
    PRIMARY KEY (`item_luid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
