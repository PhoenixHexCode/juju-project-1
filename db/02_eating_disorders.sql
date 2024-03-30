CREATE TABLE IF NOT EXISTS `eating_disorder` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(100) NOT NULL,
  `shortname` VARCHAR(10),
  `description` TEXT NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

INSERT INTO `eating_disorder` (`name`, `shortname`, `description`)
VALUES
    ('Anorexia Nervosa' ,NULL, 'Characterized by restricted food intake, an intense fear of gaining weight, and a distorted body image.'),
    ('Bulimia Nervosa', NULL, 'Involves episodes of binge eating followed by compensatory behaviors, such as vomiting, fasting, or excessive exercise.'),
    ('Binge Eating Disorder', NULL, 'Characterized by recurrent episodes of eating large quantities of food in a short period, often accompanied by feelings of loss of control and guilt.'),
    ('Avoidant/Restrictive Food Intake Disorder', 'ARFID', 'Not characterized by distress about body shape or size but involves a lack of interest in eating or food avoidance based on sensory characteristics or concerns about aversive consequences of eating.'),
    ('Pica', NULL, 'Involves eating non-food substances for a period longer than one month at an age where this behavior is developmentally inappropriate.'),
    ('Rumination Disorder', NULL, 'Characterized by the repeated regurgitation of food, which may be re-chewed, re-swallowed, or spit out.'),
    ('Other Specified Feeding or Eating Disorder', 'OSFED','Applies when symptoms cause significant distress or impairment but do not align with the criteria for other eating disorders.'),
    ('Unspecified Feeding or Eating Disorder', 'UFED', 'Used when an individual clearly has an eating disorder, but there is insufficient information to make a more specific diagnosis.');