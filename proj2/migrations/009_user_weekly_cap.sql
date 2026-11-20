ALTER TABLE "User" ADD COLUMN weekly_cap_cents INTEGER CHECK (weekly_cap_cents >= 0);
