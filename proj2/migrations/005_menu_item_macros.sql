-- Estimated nutrients per serving for each menu item (milestone P3-M3, see
-- proj2/nutrition.py). Empty when not known; the planner then does not plan the item
-- while a target on that nutrient is set.
--   protein_g, carbs_g, fat_g   grams per serving
--   sodium_mg                   milligrams per serving
--   nutrition_source            where the numbers came from, e.g. the USDA foods
--                               they were estimated from
ALTER TABLE "MenuItem" ADD COLUMN protein_g REAL CHECK (protein_g >= 0);
ALTER TABLE "MenuItem" ADD COLUMN carbs_g REAL CHECK (carbs_g >= 0);
ALTER TABLE "MenuItem" ADD COLUMN fat_g REAL CHECK (fat_g >= 0);
ALTER TABLE "MenuItem" ADD COLUMN sodium_mg INTEGER CHECK (sodium_mg >= 0);
ALTER TABLE "MenuItem" ADD COLUMN nutrition_source TEXT;
