CREATE TABLE IF NOT EXISTS `Bi_doctor_db`.`event_details_base` (
    `event_id` VARCHAR(50) NOT NULL,
    `event_date` DATETIME(6),
    `event_type` VARCHAR(30),
    `event_name` VARCHAR(30),
    `item_type` VARCHAR(20),
    `item_name` VARCHAR(100),
    `item_luid` VARCHAR(50),
    `user_id` VARCHAR(50),
    `user_name` VARCHAR(50),
    `user_role` VARCHAR(30),
    `sync_date` DATETIME(6),
    `load_time` DATETIME(6),
    PRIMARY KEY (`event_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
