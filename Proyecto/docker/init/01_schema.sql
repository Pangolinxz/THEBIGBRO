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

CREATE TABLE `inventory_audit` (
  `id` INT PRIMARY KEY AUTO_INCREMENT,
  `product_id` INT NOT NULL,
  `location_id` INT NOT NULL,
  `user_id` INT,
  `movement_type` VARCHAR(20) NOT NULL,
  `quantity` INT NOT NULL,
  `previous_stock` INT NOT NULL,
  `new_stock` INT NOT NULL,
  `observations` TEXT,
  `created_at` DATETIME NOT NULL
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

CREATE TABLE `stock_adjustment_request` (
  `id` INT PRIMARY KEY AUTO_INCREMENT,
  `product_id` INT NOT NULL,
  `location_id` INT NOT NULL,
  `system_quantity` INT NOT NULL,
  `physical_quantity` INT NOT NULL,
  `delta` INT NOT NULL,
  `reason` TEXT NOT NULL,
  `attachment_url` TEXT,
  `status` VARCHAR(32) NOT NULL DEFAULT 'pending',
  `flagged` BOOLEAN DEFAULT FALSE,
  `created_by_id` INT,
  `created_at` DATETIME NOT NULL
);

CREATE UNIQUE INDEX `inventory_index_0` ON `inventory` (`product_id`, `location_id`);

ALTER TABLE `user` ADD FOREIGN KEY (`role_id`) REFERENCES `rol` (`id`);
ALTER TABLE `inventory` ADD FOREIGN KEY (`product_id`) REFERENCES `product` (`id`);
ALTER TABLE `inventory` ADD FOREIGN KEY (`location_id`) REFERENCES `location` (`id`);
ALTER TABLE `inventory_transaction` ADD FOREIGN KEY (`product_id`) REFERENCES `product` (`id`);
ALTER TABLE `inventory_transaction` ADD FOREIGN KEY (`location_id`) REFERENCES `location` (`id`);
ALTER TABLE `inventory_transaction` ADD FOREIGN KEY (`user_id`) REFERENCES `user` (`id`);
ALTER TABLE `inventory_audit` ADD FOREIGN KEY (`product_id`) REFERENCES `product` (`id`);
ALTER TABLE `inventory_audit` ADD FOREIGN KEY (`location_id`) REFERENCES `location` (`id`);
ALTER TABLE `inventory_audit` ADD FOREIGN KEY (`user_id`) REFERENCES `user` (`id`);
ALTER TABLE `order` ADD FOREIGN KEY (`seller_id`) REFERENCES `user` (`id`);
ALTER TABLE `order_item` ADD FOREIGN KEY (`order_id`) REFERENCES `order` (`id`);
ALTER TABLE `order_item` ADD FOREIGN KEY (`product_id`) REFERENCES `product` (`id`);
ALTER TABLE `stock_alert` ADD FOREIGN KEY (`product_id`) REFERENCES `product` (`id`);
ALTER TABLE `stock_adjustment_request` ADD FOREIGN KEY (`product_id`) REFERENCES `product` (`id`);
ALTER TABLE `stock_adjustment_request` ADD FOREIGN KEY (`location_id`) REFERENCES `location` (`id`);
ALTER TABLE `stock_adjustment_request` ADD FOREIGN KEY (`created_by_id`) REFERENCES `user` (`id`);
