-- Descriptive tags for each menu item, comma-separated like diet_tags. They describe
-- the item for judging how varied a plan is; they are not rules a plan must obey.
-- Allowed values are listed in proj2/meal_tags.py. Fill them with proj2/scripts/menu_tags.py.
--   cuisine   e.g. "italian"
--   protein   e.g. "chicken, egg"  ("none" for items without one)
--   flavor    e.g. "spicy, smoky"
--   meal_type breakfast, lunch-dinner, snack, dessert
ALTER TABLE "MenuItem" ADD COLUMN cuisine TEXT;
ALTER TABLE "MenuItem" ADD COLUMN protein TEXT;
ALTER TABLE "MenuItem" ADD COLUMN flavor TEXT;
ALTER TABLE "MenuItem" ADD COLUMN meal_type TEXT;
