"""Bounded local search with interchangeable move selection and starting plans."""

from dataclasses import dataclass
from itertools import islice
from random import Random
from time import perf_counter

EPSILON = 1e-12


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


STRATEGIES = {
    "first": first_improvement,
    "best": best_improvement,
    "stochastic": stochastic_improvement,
    "sideways": best_improvement,
}


def climb(starts, neighbors, select, *, max_evaluations, seed=0, sideways_limit=0, max_starts=1):
    """Search scored neighbors lazily and share the evaluation budget across starts.

    A selector receives the candidate stream, current state, seeded RNG, and whether a
    sideways move is available. Starts and neighborhood generation are independent of
    the selector. The trace records incumbent improvements as (evaluations, seconds, score).
    """
    if max_evaluations < 1 or max_starts < 1:
        raise ValueError("Search requires positive evaluation and start limits.")
    max_starts = min(max_starts, max_evaluations)
    started = perf_counter()
    rng = Random(seed)
    best = None
    evaluations = moves = starts_tried = 0
    trace = []

    def record(candidate):
        nonlocal best
        if best is None or candidate.score > best.score + EPSILON:
            best = candidate
            trace.append((evaluations, perf_counter() - started, best.score))

    def unvisited(current, visited):
        nonlocal evaluations
        for candidate in islice(neighbors(current), limit - evaluations):
            evaluations += 1
            if candidate.state not in visited:
                yield candidate

    for index, current in enumerate(islice(starts, max_starts), 1):
        starts_tried += 1
        limit = evaluations + (max_evaluations - evaluations) // (max_starts - index + 1)
        evaluations += 1
        record(current)
        visited = {current.state}
        sideways = 0
        while evaluations < limit:
            move = select(unvisited(current, visited), current, rng, sideways < sideways_limit)
            if move is None:
                break
            sideways = sideways + 1 if abs(move.score - current.score) <= EPSILON else 0
            current = move
            visited.add(move.state)
            moves += 1
            record(move)

    if best is None:
        raise ValueError("Search requires at least one starting plan.")
    return SearchResult(
        best, evaluations, moves, starts_tried, perf_counter() - started, tuple(trace)
    )
