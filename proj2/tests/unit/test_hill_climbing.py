import pytest

from proj2.hill_climbing import STRATEGIES, Candidate, climb


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_strategies_share_a_reproducible_evaluation_budget(strategy):
    def neighbors(candidate):
        for index in (1, 2, 3):
            yield Candidate((index,), float(index))

    def run():
        return climb(
            [Candidate((0,), 0.0), Candidate((1,), 1.0)],
            neighbors,
            STRATEGIES[strategy],
            max_evaluations=6,
            max_starts=2,
            seed=7,
        )

    first, second = run(), run()
    assert first.evaluations == 6
    assert first.starts == 2
    assert first.best == second.best
    assert [score for _, _, score in first.trace] == [score for _, _, score in second.trace]


def test_sideways_moves_escape_plateau_without_revisiting():
    neighbors = {
        (0,): [Candidate((1,), 0)],
        (1,): [Candidate((0,), 0), Candidate((2,), 1)],
        (2,): [],
    }
    result = climb(
        [Candidate((0,), 0)],
        lambda current: iter(neighbors[current.state]),
        STRATEGIES["sideways"],
        max_evaluations=10,
        sideways_limit=1,
    )
    assert result.best == Candidate((2,), 1)
    assert result.moves == 2
