-- More descriptive tags for each menu item (see 003 and proj2/meal_tags.py, which lists
-- the allowed values). Text columns are comma-separated like diet_tags.
--   carb_base       e.g. "rice"           ("none" if no starch)
--   cooking_method  e.g. "grilled"
--   course          one of starter, main, side, dessert, drink
--   spice_level     0 none, 1 mild, 2 medium, 3 hot
--   temperature     hot or cold
--   texture         e.g. "crunchy, soft"
--   heaviness       light, regular or hearty
--   nutrition       e.g. "high-protein, low-carb" ("none" if nothing stands out)
--   contains        caffeine, alcohol ("none" if neither)
--   travels_well    1 if it is still good after a delivery ride, else 0
--   reheats_well    1 if it is good as leftovers, else 0
ALTER TABLE "MenuItem" ADD COLUMN carb_base TEXT;
ALTER TABLE "MenuItem" ADD COLUMN cooking_method TEXT;
ALTER TABLE "MenuItem" ADD COLUMN course TEXT;
ALTER TABLE "MenuItem" ADD COLUMN spice_level INTEGER CHECK (spice_level BETWEEN 0 AND 3);
ALTER TABLE "MenuItem" ADD COLUMN temperature TEXT;
ALTER TABLE "MenuItem" ADD COLUMN texture TEXT;
ALTER TABLE "MenuItem" ADD COLUMN heaviness TEXT;
ALTER TABLE "MenuItem" ADD COLUMN nutrition TEXT;
ALTER TABLE "MenuItem" ADD COLUMN contains TEXT;
ALTER TABLE "MenuItem" ADD COLUMN travels_well INTEGER CHECK (travels_well IN (0, 1));
ALTER TABLE "MenuItem" ADD COLUMN reheats_well INTEGER CHECK (reheats_well IN (0, 1));
