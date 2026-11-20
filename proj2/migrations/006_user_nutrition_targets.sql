-- Daily nutrition targets saved on the account (milestone P3-M3, see proj2/nutrition.py),
-- so the plan form opens with the ranges the user last planned with.
--   nutrition_targets   JSON object, MenuItem column -> {"min": int|null, "max": int|null},
--                       e.g. {"calories": {"min": 1800, "max": 2200}}; '' for none
--   strict_targets      1 when every planned day must meet every range, else 0
ALTER TABLE "User" ADD COLUMN nutrition_targets TEXT NOT NULL DEFAULT '';
ALTER TABLE "User" ADD COLUMN strict_targets INTEGER NOT NULL DEFAULT 0 CHECK (strict_targets IN (0, 1));
