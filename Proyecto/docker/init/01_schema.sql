CREATE TABLE `rol` (
  `id` INT PRIMARY KEY AUTO_INCREMENT,
  `name` VARCHAR(255) UNIQUE
);

CREATE TABLE `user` (
  `id` INT PRIMARY KEY AUTO_INCREMENT,
  `username` VARCHAR(255) UNIQUE,
  `full_name` VARCHAR(255),
  `email` VARCHAR(255) UNIQUE,
  `role_id` INT
);

CREATE TABLE `product` (
  `id` INT PRIMARY KEY AUTO_INCREMENT,
  `sku` VARCHAR(255) UNIQUE,
  `name` VARCHAR(255),
  `description` TEXT,
  `reorder_point` INT,
  `category` VARCHAR(32) NOT NULL DEFAULT 'standard'
);

CREATE TABLE `location` (
  `id` INT PRIMARY KEY AUTO_INCREMENT,
  `code` VARCHAR(255) UNIQUE,
  `description` TEXT
);

CREATE TABLE `inventory` (
  `id` INT PRIMARY KEY AUTO_INCREMENT,
  `product_id` INT,
  `location_id` INT,
  `quantity` INT,
  `updated_at` DATETIME
);

CREATE TABLE `inventory_transaction` (
  `id` INT PRIMARY KEY AUTO_INCREMENT,
  `product_id` INT,
  `location_id` INT,
  `user_id` INT,
  `type` VARCHAR(255),
  `quantity` INT,
  `created_at` DATETIME
);

CREATE TABLE `order` (
  `id` INT PRIMARY KEY AUTO_INCREMENT,
  `seller_id` INT,
  `status` VARCHAR(255),
  `created_at` DATETIME
);

CREATE TABLE `order_item` (
  `id` INT PRIMARY KEY AUTO_INCREMENT,
  `order_id` INT,
  `product_id` INT,
  `quantity` INT,
  `reserved` BOOLEAN DEFAULT FALSE
);

CREATE TABLE `stock_alert` (
  `id` INT PRIMARY KEY AUTO_INCREMENT,
  `product_id` INT,
  `triggered_at` DATETIME,
  `message` TEXT
);

CREATE UNIQUE INDEX `inventory_index_0` ON `inventory` (`product_id`, `location_id`);

ALTER TABLE `user` ADD FOREIGN KEY (`role_id`) REFERENCES `rol` (`id`);
ALTER TABLE `inventory` ADD FOREIGN KEY (`product_id`) REFERENCES `product` (`id`);
ALTER TABLE `inventory` ADD FOREIGN KEY (`location_id`) REFERENCES `location` (`id`);
ALTER TABLE `inventory_transaction` ADD FOREIGN KEY (`product_id`) REFERENCES `product` (`id`);
ALTER TABLE `inventory_transaction` ADD FOREIGN KEY (`location_id`) REFERENCES `location` (`id`);
ALTER TABLE `inventory_transaction` ADD FOREIGN KEY (`user_id`) REFERENCES `user` (`id`);
ALTER TABLE `order` ADD FOREIGN KEY (`seller_id`) REFERENCES `user` (`id`);
ALTER TABLE `order_item` ADD FOREIGN KEY (`order_id`) REFERENCES `order` (`id`);
ALTER TABLE `order_item` ADD FOREIGN KEY (`product_id`) REFERENCES `product` (`id`);
ALTER TABLE `stock_alert` ADD FOREIGN KEY (`product_id`) REFERENCES `product` (`id`);
