# Weekly budget for generated meal plans

The meal generation form accepts an optional **Weekly item-price cap**. A week
runs Monday through Sunday. For a cap of `$75.00`, every week affected by the
request must contain at most 7,500 cents in planned menu items after generation.
The generator counts meals already saved anywhere in those calendar weeks,
including meals outside the dates requested.

The cap applies to one serving of each planned meal at the catalog price. It
does not include tax, delivery or service charges, or tips. A blank cap keeps
the existing uncapped behavior. The chosen cap is used for that generation
request; it is not saved as a standing account budget.

## How candidate selection respects the cap

For every requested date and meal period, generation finds menu items that are
in stock, belong to an open restaurant serving at that time, do not contain the
user's listed allergens, and have a valid nonnegative price. Eligible items are
ordered by price and then item ID. The planner only chooses from these
candidates, so an unavailable or over-budget item can never be picked.

Before choosing anything, generation estimates the minimum spend needed to
fill every new meal slot. For each affected week, it adds the cheapest eligible
item for each requested, unfilled slot to the prices of meals already saved in
that week. If this minimum exceeds the cap, the request returns an error with
the minimum amount and leaves the database and session unchanged. The error
suggests increasing the cap or requesting fewer meals.

When the plan can fit, selection proceeds one slot at a time. Each slot's
available price is the weekly cap minus the prices already counted minus the
cheapest possible cost reserved for the other slots. This leaves room to finish
the requested plan even when the planner picks a more expensive affordable item for variety
for an earlier meal. The resulting plan is checked and totaled before it is
saved.

`MenuItem.price` and the cap calculations use integer cents. The form accepts
dollar values with no more than two decimal places. For example, `$12.34` is
1,234 cents; `$12.345`, negative values, NaN, and infinity are rejected. The API
uses the same dollar amount for `weekly_cap`:

```json
{
  "start_date": "2026-10-05",
  "meal_numbers": [3],
  "number_of_days": 7,
  "weekly_cap": "75.00"
}
```

A successful JSON response includes `weekly_cap_cents`, `item_total_cents`, and
`weekly_item_totals_cents`, keyed by the Monday date of each affected week.
For an uncapped request, missing catalog items or invalid saved prices do not
prevent generation or saving the plan; both total fields are `null` when the
affected weeks cannot be priced. Capped requests still require valid prices
for all saved meals in those weeks.
An impossible plan returns HTTP 422 and an explanation. An invalid cap returns
HTTP 400. HTML form users see the same message on the profile page.
Form errors are carried in the session and shown once after redirecting, rather
than read from URL text. Unexpected failures return a fixed retry message and
log the exception on the server.

The home calendar shows saved item totals by Monday-start week for weeks that
contain dates in the displayed month. A week at the month boundary includes its
planned meals from the neighboring month. If an old saved entry refers to an
item missing from the catalog, the page explains that it cannot calculate the
total instead of showing an inaccurate zero.

Focused tests cover exact-cap success, a cap one cent below the minimum, saved
meals counting against the cap, seven-day week boundaries, meals at the edge of
a displayed month, free meals, missing catalog prices, allergens, stock,
restaurant hours, invalid caps, and a model that repeatedly returns an excluded
item. Run them with:

```bash
CI=true .venv/bin/python -m pytest proj2/tests/unit/test_meal_budget.py \
  proj2/tests/unit/test_budget_generation.py \
  proj2/tests/integration/test_budget_generation_route.py -o addopts='' -q
```
