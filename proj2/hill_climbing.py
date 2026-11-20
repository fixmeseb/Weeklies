"""Bounded local search with interchangeable move selection and starting plans."""

from collections import deque
from dataclasses import dataclass
from itertools import islice
from math import exp
from random import Random
from time import perf_counter

EPSILON = 1e-12
INITIAL_TEMPERATURE = 0.04
FINAL_TEMPERATURE = 0.0002
TABU_TENURE = 7
LATE_ACCEPTANCE_HISTORY = 20
PERTURBATION_STEPS = 3


@dataclass(frozen=True)
class Candidate:
    state: tuple
    score: float


@dataclass(frozen=True)
class SearchResult:
    best: Candidate
    evaluations: int
    moves: int
    starts: int
    seconds: float
    trace: tuple
    initial_score: float
    best_start_score: float
    sideways_moves: int
    downhill_moves: int


def first_improvement(candidates, current, rng, allow_sideways):
    return next((move for move in candidates if move.score > current.score + EPSILON), None)


def best_improvement(candidates, current, rng, allow_sideways):
    best = max(candidates, key=lambda move: move.score, default=None)
    if best is not None and (
        best.score > current.score + EPSILON
        or (allow_sideways and best.score >= current.score - EPSILON)
    ):
        return best
    return None


def stochastic_improvement(candidates, current, rng, allow_sideways):
    improving = [move for move in candidates if move.score > current.score + EPSILON]
    return rng.choice(improving) if improving else None


def annealing_move(candidates, current, rng, temperature):
    """Test a random feasible proposal and keep the current plan on rejection."""
    proposal = next(candidates, None)
    if proposal is None:
        return None
    gain = proposal.score - current.score
    if gain >= 0 or rng.random() < exp(gain / temperature):
        return proposal
    return current


def tabu_search(_start, neighbors):
    """Take the best admissible move and temporarily block reversal of recent assignments."""
    recent = deque(maxlen=TABU_TENURE)

    def choose(current, incumbent):
        blocked = {assignment for removed in recent for assignment in removed}
        winner = None
        for move in neighbors(current):
            if move.score <= incumbent.score + EPSILON and any(
                old != new and (index, new) in blocked
                for index, (old, new) in enumerate(zip(current.state, move.state))
            ):
                continue
            if winner is None or move.score > winner.score:
                winner = move
        if winner is not None:
            recent.append(
                tuple(
                    (index, old)
                    for index, (old, new) in enumerate(zip(current.state, winner.state))
                    if old != new
                )
            )
        return winner

    return choose


def late_acceptance(start, neighbors):
    """Compare each random proposal with both the current and an earlier score."""
    history = deque([start.score] * LATE_ACCEPTANCE_HISTORY, maxlen=LATE_ACCEPTANCE_HISTORY)

    def choose(current, _incumbent):
        proposal = next(neighbors(current, randomize=True), None)
        if proposal is None:
            return None
        threshold = min(current.score, history[0])
        move = proposal if proposal.score >= threshold - EPSILON else current
        history.append(move.score)
        return move

    return choose


def iterated_local_search(_start, neighbors):
    """Alternate best-improvement climbs to local optima with random perturbations."""
    remaining = 0

    def choose(current, _incumbent):
        nonlocal remaining
        if remaining == 0:
            improvement = max(neighbors(current), key=lambda move: move.score, default=None)
            if improvement is not None and improvement.score > current.score + EPSILON:
                return improvement
            remaining = PERTURBATION_STEPS
        remaining -= 1
        return next(neighbors(current, randomize=True), None)

    return choose


_STATEFUL_STRATEGIES = {
    "tabu": tabu_search,
    "late-acceptance": late_acceptance,
    "iterated": iterated_local_search,
}

STRATEGIES = {
    "first": first_improvement,
    "best": best_improvement,
    "stochastic": stochastic_improvement,
    "sideways": best_improvement,
    "annealing": annealing_move,
    **_STATEFUL_STRATEGIES,
}


def climb(
    starts,
    neighbors,
    select,
    *,
    max_evaluations,
    seed=0,
    sideways_limit=0,
    max_starts=1,
    randomized_neighbors=None,
):
    """Search scored neighbors lazily and share the evaluation budget across starts.

    A selector receives the candidate stream, current state, seeded RNG, and whether a
    sideways move is available. Annealing instead receives the temperature, can revisit
    plans, and uses randomized_neighbors(current, rng) to propose a feasible random move
    when provided. Stateful strategies initialize their own move rules at each start.
    The trace records incumbent improvements as (evaluations, seconds, score).
    """
    if max_evaluations < 1 or max_starts < 1:
        raise ValueError("Search requires positive evaluation and start limits.")
    max_starts = min(max_starts, max_evaluations)
    started = perf_counter()
    rng = Random(seed)
    best = None
    initial_score = best_start_score = None
    annealing = select is annealing_move
    stateful = select in _STATEFUL_STRATEGIES.values()
    evaluations = moves = starts_tried = sideways_moves = downhill_moves = 0
    trace = []

    def record(candidate):
        nonlocal best
        if best is None or candidate.score > best.score + EPSILON:
            best = candidate
            trace.append((evaluations, perf_counter() - started, best.score))

    def evaluated_neighbors(current, visited=None, *, randomize=False):
        nonlocal evaluations
        source = (
            randomized_neighbors(current, rng)
            if randomize and randomized_neighbors is not None
            else neighbors(current)
        )
        for candidate in islice(source, limit - evaluations):
            evaluations += 1
            if candidate.state != current.state and (
                visited is None or candidate.state not in visited
            ):
                yield candidate

    for index, current in enumerate(islice(starts, max_starts), 1):
        starts_tried += 1
        limit = evaluations + (max_evaluations - evaluations) // (max_starts - index + 1)
        initial_score = current.score if initial_score is None else initial_score
        best_start_score = (
            current.score if best_start_score is None else max(best_start_score, current.score)
        )
        evaluations += 1
        first_proposal = evaluations
        record(current)
        choose = select(current, evaluated_neighbors) if stateful else None
        visited = None if annealing or stateful else {current.state}
        sideways = 0
        while evaluations < limit:
            if annealing:
                progress = (evaluations - first_proposal) / max(1, limit - first_proposal - 1)
                temperature = (
                    INITIAL_TEMPERATURE * (FINAL_TEMPERATURE / INITIAL_TEMPERATURE) ** progress
                )
                move = select(
                    evaluated_neighbors(current, randomize=True), current, rng, temperature
                )
            elif choose is not None:
                move = choose(current, best)
            else:
                move = select(
                    evaluated_neighbors(current, visited), current, rng, sideways < sideways_limit
                )
            if move is None:
                break
            if move.state == current.state:
                continue
            gain = move.score - current.score
            if abs(gain) <= EPSILON:
                sideways += 1
                sideways_moves += 1
            else:
                sideways = 0
                downhill_moves += gain < -EPSILON
            current = move
            if visited is not None:
                visited.add(move.state)
            moves += 1
            record(move)

    if best is None:
        raise ValueError("Search requires at least one starting plan.")
    return SearchResult(
        best,
        evaluations,
        moves,
        starts_tried,
        perf_counter() - started,
        tuple(trace),
        initial_score,
        best_start_score,
        sideways_moves,
        downhill_moves,
    )
