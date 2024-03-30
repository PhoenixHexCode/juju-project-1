
-- Dumping database structure for project1-db
CREATE DATABASE IF NOT EXISTS `project1-db` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci */ /*!80016 DEFAULT ENCRYPTION='N' */;
USE `project1-db`;

-- Dumping structure for table project1-db.token_usage
CREATE TABLE IF NOT EXISTS `token_usage` (
  `id` int NOT NULL AUTO_INCREMENT,
  `message` json DEFAULT NULL,
  `response` json DEFAULT NULL,
  `tokens` int NOT NULL DEFAULT '0',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Data exporting was unselected.
