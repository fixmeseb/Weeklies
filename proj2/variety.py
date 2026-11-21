"""
How different the meals in a plan are from each other.

Two meals are compared tag by tag (proj2/meal_tags.py), and each tag kind gives a
distance from 0 (same) to 1 (nothing in common). The meal distance is the weighted
average of those, so a tag with many values (flavor) cannot outweigh the ones that
matter most (protein, cuisine). A tag missing on either meal is left out and the rest
re-averaged; it counts neither as a match nor as a difference.

**Absent tags.** Re-averaging alone is not enough, because it reads a pair that could
barely be compared as confidently as one that could be compared on everything. Two tag
kinds are never missing -- `item` (itm_id) and `restaurant` (rtr_id) are on every
catalog row -- and both almost always differ, `item` by definition for any two distinct
dishes. For a dish with no descriptive tags those two are the *only* comparable kinds,
carrying 5.0 of the 19.5 total weight, so re-averaging over them alone gave such a dish
the maximum possible distance against anything at another restaurant:

    an untagged dish vs any dish elsewhere                       1.000
    two fully tagged dishes, as unlike as the seeded catalog gets  0.987

The planner maximizes distance, so the best possible meal was one nobody had described.
Five untagged dishes added to the 76-dish seeded catalog took 2 of 5 planned slots and
raised the reported variety score from 0.937 to 0.965 -- the product claiming a week was
*more* varied for containing food it knew nothing about.

So the re-averaged distance is pulled toward NEUTRAL_DISTANCE in proportion to the
weight that could not be compared. A fully tagged pair is unaffected, while the
untagged pair above falls to 0.628 and can no longer outrank a genuinely varied one.
Absent data says "unknown", not "different". This is the scoring half of the guard
proj2/menu_items.py applies at the gate: that one keeps new dishes from entering the
catalog untagged, this one stops the dishes already in it from being preferred for it.

A plan's score is the average distance between its meals, weighted by how close they
are in time: two chicken dinners in a row cost more than two a week apart. Because those
closeness weights depend only on which slots are filled, not on what fills them, a
planner maximizes the score by maximizing each slot's weighted distance to its
neighbours (slot_gain), which is what proj2.menu_generation and the swap options do.

Tags left out on purpose: meal_type and course (the slot decides them, so they would
reward a breakfast for differing from a dinner), and diet_tags, allergens, nutrition,
contains, travels_well and reheats_well (rules and practical traits, not what the meal
is like to eat).
"""

import datetime
from dataclasses import dataclass, field

from proj2 import meal_tags
from proj2.dietary import KNOWN_DIETS, normalize_tag

## Relative importance of each tag kind in the distance between two meals.
## "item" is 0 for the same dish and 1 otherwise, so an exact repeat is always the
## closest pair, even in a catalog with no tags at all.
WEIGHTS = {
    "protein": 3.0,
    "cuisine": 3.0,
    "carb_base": 2.0,
    "cooking_method": 2.0,
    "restaurant": 2.0,
    "flavor": 1.5,
    "texture": 1.0,
    "spice_level": 1.0,
    "item": 3.0,
    "heaviness": 0.5,
    "temperature": 0.5,
}

## What an unmeasurable comparison is worth: the midpoint, meaning "no evidence either
## way". distance() pulls a pair toward this in proportion to the weight it could not
## compare, so a pair that could barely be compared cannot score at either extreme.
## See "Absent tags" in the module docstring.
NEUTRAL_DISTANCE = 0.5

## Tag kinds compared as sets of tags (Jaccard distance)
SET_COLUMNS = ("protein", "cuisine", "carb_base", "cooking_method", "flavor", "texture")

HEAVINESS_ORDER = {"light": 0, "regular": 1, "hearty": 2}
SPICE_RANGE = meal_tags.COLUMNS["spice_level"].high - meal_tags.COLUMNS["spice_level"].low

## Closeness weight halves every this many slots (3 slots = 1 day)...
HALF_LIFE_SLOTS = 3
## ...and is 0 for meals further apart than this
WINDOW_DAYS = 7
SLOTS_PER_DAY = 3

## How much a soft preference ("Italian", "spicy") counts, as a share of the 0-1
## variety score of one slot: enough to break near-ties, not to override variety
PREFERENCE_WEIGHT = 0.15

## Tag kinds a soft preference word is matched against
PREFERENCE_COLUMNS = ("cuisine", "flavor", "protein")


def _missing(value) -> bool:
    return value is None or value != value or (isinstance(value, str) and not value.strip())


def _get(item, key):
    try:
        return item.get(key)
    except AttributeError:  # sqlite3.Row has no get()
        return item[key] if key in item.keys() else None


def features(item) -> dict:
    """
    Reads the tags that variety compares from one menu item

    Args:
        item (Mapping): A MenuItem row (dict, pandas Series or sqlite3.Row); missing
            columns and empty cells are allowed

    Returns:
        dict: One entry per key of WEIGHTS; None where the item is not tagged
    """
    out = {}
    for column in SET_COLUMNS:
        tags = meal_tags.parse_tags(column, _get(item, column))
        out[column] = frozenset(tags) if tags else None
    spice = _get(item, "spice_level")
    out["spice_level"] = None if _missing(spice) else int(spice)
    heaviness = meal_tags.parse_tags("heaviness", _get(item, "heaviness"))
    out["heaviness"] = HEAVINESS_ORDER.get(next(iter(heaviness))) if len(heaviness) == 1 else None
    temperature = meal_tags.parse_tags("temperature", _get(item, "temperature"))
    out["temperature"] = next(iter(temperature)) if len(temperature) == 1 else None
    for key, column in (("restaurant", "rtr_id"), ("item", "itm_id")):
        value = _get(item, column)
        out[key] = None if _missing(value) else int(value)
    return out


def _column_distance(column: str, a, b) -> float:
    if column in SET_COLUMNS:
        return 1.0 - len(a & b) / len(a | b)
    if column == "spice_level":
        return abs(a - b) / SPICE_RANGE
    if column == "heaviness":
        return abs(a - b) / (len(HEAVINESS_ORDER) - 1)
    return 0.0 if a == b else 1.0


def distance(a: dict, b: dict, weights: dict = WEIGHTS) -> float:
    """
    How different two meals are, from 0 (same) to 1 (nothing in common)

    Tags missing on either meal are left out and the rest re-averaged, then the result
    is pulled toward NEUTRAL_DISTANCE in proportion to the weight that was missing. The
    re-average alone is what UNKNOWN_IS_NOT_DIFFERENT describes: it reads a pair that
    could barely be compared as confidently as one that could be compared on everything,
    and for an untagged dish the only comparable tags are the two that are always
    present and almost always differ.

    Args:
        a (dict): features() of one meal
        b (dict): features() of the other
        weights (dict): Weight per tag kind (default WEIGHTS)

    Returns:
        float: 0 (same) to 1 (nothing in common); NEUTRAL_DISTANCE when the two meals
            share no tag kind at all, because nothing was learned either way
    """
    # The same dish is the one comparison that is never uncertain, so it is never
    # shrunk: an exact repeat stays the closest possible pair even with no tags at all,
    # which is what WEIGHTS promises and what stops a plan repeating one untagged dish.
    if a.get("item") is not None and a.get("item") == b.get("item"):
        return 0.0
    total = weight_sum = 0.0
    for column, weight in weights.items():
        x, y = a.get(column), b.get(column)
        if x is None or y is None:
            continue
        total += weight * _column_distance(column, x, y)
        weight_sum += weight
    if not weight_sum:
        return NEUTRAL_DISTANCE
    observed = total / weight_sum
    coverage = weight_sum / sum(weights.values())
    return observed * coverage + NEUTRAL_DISTANCE * (1.0 - coverage)


def shared_tags(a: dict, b: dict) -> list:
    """
    What two meals have in common, for explaining why they count as similar

    Returns:
        List[str]: e.g. ["same dish"] or ["protein: chicken", "carb_base: rice"]
    """
    if a.get("item") is not None and a.get("item") == b.get("item"):
        return ["same dish"]
    shared = []
    if a.get("restaurant") is not None and a.get("restaurant") == b.get("restaurant"):
        shared.append("same restaurant")
    for column in SET_COLUMNS:
        common = (a.get(column) or frozenset()) & (b.get(column) or frozenset())
        common -= {"none"}
        if common:
            shared.append(f"{column}: {', '.join(sorted(common))}")
    return shared


def slot_position(day: str, meal: int) -> int:
    """A slot's place in time, counted in meal slots (3 per day)."""
    return datetime.date.fromisoformat(day).toordinal() * SLOTS_PER_DAY + (int(meal) - 1)


def closeness(position_a: int, position_b: int) -> float:
    """
    How much the distance between two slots counts toward the score

    Returns:
        float: 1.0 for neighbouring slots, halving every HALF_LIFE_SLOTS slots, and 0.0
            for the same slot or slots more than WINDOW_DAYS apart
    """
    gap = abs(position_a - position_b)
    if gap == 0 or gap > WINDOW_DAYS * SLOTS_PER_DAY:
        return 0.0
    return 0.5 ** ((gap - 1) / HALF_LIFE_SLOTS)


def slot_gain(candidate: dict, position: int, neighbours, weights: dict = WEIGHTS):
    """
    How much variety one meal adds next to the meals already planned around it

    Args:
        candidate (dict): features() of the meal being considered
        position (int): slot_position() of the slot it would fill
        neighbours (Iterable[Tuple[int, dict]]): (position, features) of the other planned meals
        weights (dict): Weight per tag kind

    Returns:
        Tuple[float, float]: (sum of closeness * distance, sum of closeness)
    """
    return _weighted_gain(position, neighbours, lambda other: distance(candidate, other, weights))


def _weighted_gain(position: int, neighbours, distance_to) -> tuple:
    """(sum of closeness * distance_to(other), sum of closeness) over (position, other) pairs."""
    gain = weight_sum = 0.0
    for other_position, other in neighbours:
        w = closeness(position, other_position)
        if w:
            gain += w * distance_to(other)
            weight_sum += w
    return gain, weight_sum


class ItemDistances:
    """
    distance() between catalog items by itm_id, each pair computed once

    A planner compares every candidate with the same few planned meals slot after slot,
    so features and pair distances are cached. Build a new one whenever the catalog or
    the weights change.
    """

    def __init__(self, rows, weights: dict = WEIGHTS):
        """
        Args:
            rows (Mapping[int, Mapping]): MenuItem rows by itm_id
            weights (dict): Weight per tag kind
        """
        self.rows = rows
        self.weights = weights
        self._features = {}
        self._distances = {}

    def features(self, itm_id: int) -> dict:
        if itm_id not in self._features:
            self._features[itm_id] = features(self.rows[itm_id])
        return self._features[itm_id]

    def distance(self, a: int, b: int) -> float:
        key = (a, b) if a <= b else (b, a)
        if key not in self._distances:
            self._distances[key] = distance(self.features(a), self.features(b), self.weights)
        return self._distances[key]

    def slot_gain(self, itm_id: int, position: int, neighbours):
        """
        slot_gain() for one catalog item

        Args:
            itm_id (int): The candidate item
            position (int): slot_position() of the slot it would fill
            neighbours (Iterable[Tuple[int, int]]): (position, itm_id) of the other planned meals

        Returns:
            Tuple[float, float]: (sum of closeness * distance, sum of closeness)
        """
        return _weighted_gain(position, neighbours, lambda other: self.distance(itm_id, other))


def soft_preferences(preferences) -> set:
    """The preference words that are not diets (diets are hard rules), normalized."""
    words = {normalize_tag(word) for word in (preferences or "").split(",") if word.strip()}
    return words - KNOWN_DIETS


def preference_match(item, preferences) -> float:
    """
    The share of a user's soft preferences that one item matches

    A word matches when it is one of the item's cuisine, flavor or protein tags
    (after the same spelling rules as the tag import, so "Middle Eastern" matches).

    Args:
        item (Mapping): A MenuItem row
        preferences (str | None): The user's comma-separated preferences

    Returns:
        float: From 0 (no soft preference matched, or none given) to 1 (all matched)
    """
    wanted = soft_preferences(preferences)
    if not wanted:
        return 0.0
    matched = set()
    for column in PREFERENCE_COLUMNS:
        tags = meal_tags.parse_tags(column, _get(item, column))
        matched |= {word for word in wanted if meal_tags.normalize(column, word) in tags}
    return len(matched) / len(wanted)


def candidate_score(gain: float, weight_sum: float, preference: float) -> float:
    """
    The value of filling a slot with one item: its share of possible variety plus the
    preference bonus. Rounded so float noise cannot decide a tie.
    """
    share = gain / weight_sum if weight_sum else 0.0
    return round(share + PREFERENCE_WEIGHT * preference, 9)


@dataclass
class PlanVariety:
    """The variety of a set of planned meals."""

    score: float = None  # 0-1, or None if no two meals are close enough to compare
    pairs: list = field(default_factory=list)  # (closeness, distance, entry_a, entry_b)
    features: dict = field(default_factory=dict)  # itm_id -> features()

    def similar_pairs(self, limit: int = 3) -> list:
        """
        The nearby pairs that cost the most variety, most costly first

        Returns:
            List[dict]: {"a", "b": {"date", "meal", "itm_id"}, "similarity", "shared"}
        """
        ranked = sorted(self.pairs, key=lambda p: (-p[0] * (1 - p[1]), p[2], p[3]))
        out = []
        for w, d, a, b in ranked[:limit]:
            if w * (1 - d) <= 0:
                break
            out.append(
                {
                    "a": {"date": a[0], "itm_id": a[1], "meal": a[2]},
                    "b": {"date": b[0], "itm_id": b[1], "meal": b[2]},
                    "similarity": round(1 - d, 3),
                    "shared": shared_tags(self.features[a[1]], self.features[b[1]]),
                }
            )
        return out

    def as_json(self, limit: int = 3) -> dict:
        score = None if self.score is None else round(self.score, 3)
        return {"score": score, "similar_pairs": self.similar_pairs(limit)}


def plan_variety(entries, items, weights: dict = WEIGHTS) -> PlanVariety:
    """
    Scores how varied a set of planned meals is

    Args:
        entries (Iterable[Tuple[str, int, int]]): (date, itm_id, meal) for each planned meal,
            e.g. from proj2.meal_budget.plan_entries
        items (Mapping[int, Mapping]): MenuItem rows by itm_id; meals whose item is missing
            are left out
        weights (dict): Weight per tag kind

    Returns:
        PlanVariety: The score (sum of closeness * distance over sum of closeness, across
            every pair of meals) and the pairs it was computed from
    """
    report = PlanVariety()
    entries = sorted({e for e in entries if e[1] in items}, key=lambda e: slot_position(e[0], e[2]))
    for _, itm_id, _ in entries:
        if itm_id not in report.features:
            report.features[itm_id] = features(items[itm_id])
    positions = [slot_position(day, meal) for day, _, meal in entries]
    total = weight_sum = 0.0
    for i, a in enumerate(entries):
        for j in range(i + 1, len(entries)):
            w = closeness(positions[i], positions[j])
            if not w:
                continue
            b = entries[j]
            d = distance(report.features[a[1]], report.features[b[1]], weights)
            report.pairs.append((w, d, a, b))
            total += w * d
            weight_sum += w
    report.score = total / weight_sum if weight_sum else None
    return report


def catalog_rows(conn) -> dict:
    """
    Every menu item's columns by itm_id, for scoring plans read from the database

    Args:
        conn (sqlite3.Connection): An open database connection

    Returns:
        dict: itm_id -> {column: value}
    """
    cursor = conn.execute('SELECT * FROM "MenuItem"')
    columns = [d[0] for d in cursor.description]
    key = columns.index("itm_id")
    return {row[key]: dict(zip(columns, row)) for row in cursor.fetchall()}
