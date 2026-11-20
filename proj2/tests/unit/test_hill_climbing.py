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


def test_annealing_crosses_a_downhill_barrier_and_returns_the_best_plan():
    start = Candidate((0,), 0.5)
    barrier = Candidate((1,), 0.495)
    peak = Candidate((2,), 0.8)
    finish = Candidate((3,), 0.79999)
    graph = {start.state: [barrier], barrier.state: [peak], peak.state: [finish]}

    def neighbors(current):
        return iter(graph.get(current.state, ()))

    greedy = climb([start], neighbors, STRATEGIES["best"], max_evaluations=4)
    annealing = climb([start], neighbors, STRATEGIES["annealing"], max_evaluations=4, seed=0)
    assert greedy.best == start
    assert annealing.best == peak
    assert annealing.best_start_score == start.score
    assert annealing.evaluations == 4
    assert annealing.moves == 3
    assert annealing.downhill_moves == 2


def test_tabu_blocks_a_recent_reversal_but_allows_a_new_record():
    start = Candidate((0, 0), 0.50)
    first = Candidate((1, 0), 0.49)
    second = Candidate((1, 1), 0.48)
    record = Candidate((0, 1), 0.80)
    alternate = Candidate((1, 2), 0.60)
    graph = {
        start.state: [first],
        first.state: [start, second],
        second.state: [alternate, record],
    }
    result = climb(
        [start],
        lambda current: iter(graph.get(current.state, ())),
        STRATEGIES["tabu"],
        max_evaluations=6,
    )
    assert result.best == record
    assert result.moves == 3
    assert result.downhill_moves == 2


def test_late_acceptance_can_drop_from_the_current_score_to_an_earlier_threshold():
    start = Candidate((0,), 0.40)
    local_peak = Candidate((1,), 0.70)
    too_low = Candidate((2,), 0.30)
    accepted = Candidate((3,), 0.55)
    record = Candidate((4,), 0.80)
    proposals = {
        start.state: iter([local_peak]),
        local_peak.state: iter([too_low, accepted]),
        accepted.state: iter([record]),
    }
    result = climb(
        [start],
        lambda current: iter(()),
        STRATEGIES["late-acceptance"],
        max_evaluations=5,
        randomized_neighbors=lambda current, rng: proposals[current.state],
    )
    assert result.best == record
    assert result.evaluations == 5
    assert result.moves == 3
    assert result.downhill_moves == 1


def test_iterated_local_search_perturbs_a_local_optimum_then_climbs_again():
    start = Candidate((0,), 0.60)
    perturbations = [Candidate((1,), 0.59), Candidate((2,), 0.55), Candidate((3,), 0.45)]
    record = Candidate((4,), 0.80)
    graph = {start.state: [perturbations[0]], perturbations[-1].state: [record]}
    proposals = {
        previous.state: [move] for previous, move in zip([start, *perturbations], perturbations)
    }
    result = climb(
        [start],
        lambda current: iter(graph[current.state]),
        STRATEGIES["iterated"],
        max_evaluations=6,
        randomized_neighbors=lambda current, rng: iter(proposals[current.state]),
    )
    assert result.best == record
    assert result.evaluations == 6
    assert result.moves == 4
    assert result.downhill_moves == 3
