"""Exact money and calendar-week accounting for meal plans (item prices only)."""

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import re


class BudgetExceededError(ValueError):
    """The requested meals cannot fit the weekly item-price cap."""


def parse_weekly_cap(value):
    """Convert an optional dollar amount to integer cents without rounding it."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        amount = Decimal(str(value))
        # The saved amount must fit in SQLite's signed 64-bit cents column.
        if not amount.is_finite() or not 0 <= amount <= Decimal("92233720368547758.07"):
            raise ValueError
        if amount != amount.quantize(Decimal("0.01")):
            raise ValueError
        return int(amount * 100)
    except (InvalidOperation, ValueError):
        raise ValueError(
            "Weekly cap must be a nonnegative dollar amount with at most two decimals."
        )


def item_price_cents(value):
    """Validate a catalog price already stored in cents; never treat missing as free."""
    try:
        cents = Decimal(str(value))
        if not cents.is_finite() or cents < 0 or cents != cents.to_integral_value():
            raise ValueError
        return int(cents)
    except (InvalidOperation, ValueError):
        raise ValueError("A planned item has an invalid price.")


def week_start(day):
    """Return the Monday containing an ISO date, including across year boundaries."""
    day = date.fromisoformat(day)
    return (day - timedelta(days=day.weekday())).isoformat()


def plan_entries(menu):
    """Read saved entries, including legacy entries whose meal defaults to dinner."""
    entries = re.findall(
        r"\[\s*(\d{4}-\d{2}-\d{2})\s*,\s*(\d+)\s*(?:,\s*([123])\s*)?\]", menu or ""
    )
    for day, item, meal in entries:
        yield day, int(item), int(meal or 3)


def weekly_item_totals(menu, prices, weeks=None, *, excluding_slot=None):
    """Sum every saved serving in the selected weeks, optionally omitting one slot."""
    totals = {week: 0 for week in weeks} if weeks is not None else {}
    for day, item, meal in plan_entries(menu):
        if (day, meal) == excluding_slot:
            continue
        week = week_start(day)
        if weeks is not None and week not in totals:
            continue
        if item not in prices:
            raise ValueError(f"Cannot total planned item {item}: it is no longer in the catalog.")
        totals[week] = totals.get(week, 0) + item_price_cents(prices[item])
    return totals
