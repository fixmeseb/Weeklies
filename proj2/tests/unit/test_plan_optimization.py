import pandas as pd
import pytest

from proj2.hill_climbing import best_improvement, climb
from proj2.plan_optimization import MealSearch
from proj2.variety import ItemDistances


@pytest.mark.parametrize(("objective", "winner"), [(3, 2), (4, 3), (5, 4)])
def test_new_objectives_score_replacements_and_choose_the_expected_meal(objective, winner):
    rows = {
        1: {"rtr_id": 1, "calories": 700, "spice_level": 3},
        2: {"rtr_id": 1, "calories": 300, "spice_level": 2},
        3: {"rtr_id": 1, "calories": 500, "spice_level": 0},
        4: {"rtr_id": 2, "calories": 600, "spice_level": 2},
        5: {"rtr_id": 1, "calories": 600, "spice_level": 2},
        6: {"rtr_id": 1, "calories": None, "spice_level": None},
    }
    options = [
        {"position": 1, "candidates": pd.DataFrame({"itm_id": [5]})},
        {"position": 2, "candidates": pd.DataFrame({"itm_id": [1, 2, 3, 4, 6]})},
    ]
    weights = tuple(float(index == objective) for index in range(6))
    problem = MealSearch(
        options,
        {},
        {},
        dict.fromkeys(rows, 500),
        rows,
        {},
        ItemDistances(rows),
        weights,
        None,
        None,
    )
    start = problem.candidate((5, 1))
    for neighbor in problem.neighbors(start):
        assert neighbor.score == pytest.approx(problem.candidate(neighbor.state).score)
    result = climb([start], problem.neighbors, best_improvement, max_evaluations=20)
    assert result.best.state == (5, winner)
