"""Plan-level objectives and feasible neighborhoods for hill climbing."""

from collections import Counter
from dataclasses import dataclass
from math import isfinite

from proj2.hill_climbing import Candidate
from proj2.variety import ItemDistances, closeness

OBJECTIVES = {
    "variety": "More variety",
    "cost": "Lower item cost",
    "preference": "Match food preferences",
    "calories": "Lower calories",
    "mildness": "Milder meals",
    "restaurants": "More distinct restaurants",
}
VARIETY_ONLY = (1.0, 0.0, 0.0)


def parse_weights(values):
    """Normalize optional relative weights supplied by the planner form or JSON API."""
    if all(value is None or value == "" for value in values):
        return None
    message = "Enter optimization weights from 0 to 100, with at least one above zero."
    if any(isinstance(value, bool) for value in values):
        raise ValueError(message)
    try:
        weights = tuple(float(value) if value not in (None, "") else 0.0 for value in values)
    except (ValueError, TypeError, OverflowError):
        raise ValueError(message) from None
    if any(not 0 <= weight <= 100 for weight in weights) or not sum(weights):
        raise ValueError(message)
    return tuple(weight / sum(weights) for weight in weights)


@dataclass
class MealSearch:
    slots: list
    fixed: dict
    all_saved: dict
    prices: dict
    catalog: dict
    preference: dict
    distances: ItemDistances
    weights: tuple
    weekly_cap: int | None
    saved_totals: dict | None
    history: tuple = ()
    replacement_allowed: object = None

    def __post_init__(self):
        # Keep accepting the original three weights from existing planner callers.
        self.weights = (*self.weights, *(0.0,) * (len(OBJECTIVES) - len(self.weights)))
        self.positions = tuple(slot["position"] for slot in self.slots)
        self.pools = [tuple(map(int, slot["candidates"].itm_id)) for slot in self.slots]
        positions = tuple(self.fixed) + self.positions
        self.pairs = [
            (a, b, weight)
            for i, a in enumerate(positions)
            for b in positions[i + 1 :]
            if (weight := closeness(a, b))
        ]
        self.pair_weight = sum(weight for _, _, weight in self.pairs)
        self.links = {
            position: [
                (b if a == position else a, weight)
                for a, b, weight in self.pairs
                if position in (a, b)
            ]
            for position in self.positions
        }
        self.min_cost = sum(min(self.prices[item] for item in pool) for pool in self.pools)
        self.max_cost = sum(max(self.prices[item] for item in pool) for pool in self.pools)
        self.history_links = {
            position: [
                (item, weight)
                for previous, item in self.history
                if (weight := closeness(previous, position))
            ]
            for position in self.positions
        }
        history_weight = sum(weight for links in self.history_links.values() for _, weight in links)
        self.variety_factor = self.weights[0] / ((self.pair_weight + history_weight) or 1)
        self.cost_factor = self.weights[1] / (self.max_cost - self.min_cost or 1)
        self.preference_factor = self.weights[2] / (len(self.slots) or 1)
        self.calorie_factor = self.weights[3] / (len(self.slots) or 1)
        self.mildness_factor = self.weights[4] / (len(self.slots) or 1)
        self.restaurant_factor = self.weights[5] / (len(self.slots) or 1)
        self.restaurants = {item: row["rtr_id"] for item, row in self.catalog.items()}
        self.spice = {item: self.distances.features(item)["spice_level"] for item in self.catalog}
        self.calories = {}
        for item, row in self.catalog.items():
            value = row.get("calories")
            if isinstance(value, (int, float)) and isfinite(value) and value > 0:
                self.calories[item] = value
        min_calories = min(self.calories.values(), default=0)
        max_calories = max(self.calories.values(), default=0)
        calorie_range = max_calories - min_calories or 1
        self.calorie_utility = {
            item: (max_calories - value) / calorie_range for item, value in self.calories.items()
        }
        self.mildness_utility = {
            item: 1 - level / 3 for item, level in self.spice.items() if level is not None
        }

    def measure(self, state):
        planned = self.fixed | dict(zip(self.positions, state))
        distance = sum(
            weight * self.distances.distance(planned[a], planned[b]) for a, b, weight in self.pairs
        )
        calories = [self.calories[item] for item in state if item in self.calories]
        spice = [self.spice[item] for item in state if self.spice[item] is not None]
        return {
            "variety": distance / self.pair_weight if self.pair_weight else None,
            "item_cost_cents": sum(self.prices[item] for item in state),
            "preference_match": (
                sum(self.preference[item] for item in state) / len(state)
                if self.preference and state
                else None
            ),
            "average_calories": sum(calories) / len(calories) if calories else None,
            "average_spice": sum(spice) / len(spice) if spice else None,
            "distinct_restaurants": len({self.restaurants[item] for item in state}),
        }

    def candidate(self, state):
        metrics = self.measure(state)
        history_gain = sum(
            weight * self.distances.distance(item, old)
            for item, position in zip(state, self.positions)
            for old, weight in self.history_links[position]
        )
        score = (
            self.variety_factor * ((metrics["variety"] or 0.0) * self.pair_weight + history_gain)
            + self.cost_factor * (self.max_cost - metrics["item_cost_cents"])
            + self.weights[2] * (metrics["preference_match"] or 0.0)
            + self.calorie_factor * sum(self.calorie_utility.get(item, 0.0) for item in state)
            + self.mildness_factor * sum(self.mildness_utility.get(item, 0.0) for item in state)
            + self.restaurant_factor * metrics["distinct_restaurants"]
        )
        return Candidate(state, score)

    def neighbors(self, current):
        state = current.state
        planned = self.fixed | dict(zip(self.positions, state))
        counts = Counter(self.all_saved.values())
        counts.update(state)
        restaurant_counts = Counter(self.restaurants[item] for item in state)
        totals = dict(self.saved_totals or {})
        if self.weekly_cap is not None:
            for slot, item in zip(self.slots, state):
                totals[slot["week"]] += self.prices[item]
        for index, (slot, pool, old) in enumerate(zip(self.slots, self.pools, state)):
            links = [
                (planned[position], weight) for position, weight in self.links[slot["position"]]
            ]
            links.extend(self.history_links[slot["position"]])
            for item in pool:
                if item == old or (counts[item] and counts[old] == 1):
                    continue
                cost_change = self.prices[item] - self.prices[old]
                if (
                    self.weekly_cap is not None
                    and totals[slot["week"]] + cost_change > self.weekly_cap
                ):
                    continue
                if self.replacement_allowed and not self.replacement_allowed(
                    slot["position"], item, planned
                ):
                    continue
                distance_change = 0.0
                if self.variety_factor:
                    distance_change = sum(
                        weight
                        * (
                            self.distances.distance(item, other)
                            - self.distances.distance(old, other)
                        )
                        for other, weight in links
                    )
                change = (
                    self.variety_factor * distance_change
                    - self.cost_factor * cost_change
                    + self.preference_factor
                    * (self.preference.get(item, 0.0) - self.preference.get(old, 0.0))
                    + self.calorie_factor
                    * (self.calorie_utility.get(item, 0.0) - self.calorie_utility.get(old, 0.0))
                    + self.mildness_factor
                    * (self.mildness_utility.get(item, 0.0) - self.mildness_utility.get(old, 0.0))
                )
                if self.restaurant_factor and self.restaurants[item] != self.restaurants[old]:
                    change += self.restaurant_factor * (
                        int(restaurant_counts[self.restaurants[item]] == 0)
                        - int(restaurant_counts[self.restaurants[old]] == 1)
                    )
                yield Candidate(
                    state[:index] + (item,) + state[index + 1 :], current.score + change
                )
