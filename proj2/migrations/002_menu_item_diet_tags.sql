-- Diets each menu item satisfies, comma-separated (e.g. "vegan, gluten-free").
-- Diet rules fail closed: an item with no tags is excluded for any user with a diet.
-- Fill tags with proj2/scripts/diet_tags.py.
ALTER TABLE "MenuItem" ADD COLUMN diet_tags TEXT;
