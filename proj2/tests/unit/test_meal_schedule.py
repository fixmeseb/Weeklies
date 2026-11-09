import pytest

from proj2.meal_schedule import (
    COOK,
    ORDER,
    CookTimes,
    ScheduleInfeasibleError,
    cook_days,
    daily_minutes,
    order_days,
    parse_minutes,
    plan_cook_or_order,
)

MON = "2026-11-09"
TUE = "2026-11-10"


@pytest.mark.parametrize("value, expected", [(0, 0), (45, 45), ("20", 20), ("0", 0)])
def test_parse_whole_minutes(value, expected):
    assert parse_minutes(value) == expected


@pytest.mark.parametrize("value", [-1, "-5", "20.5", "NaN", "Infinity", "soon", None, True, False])
def test_reject_anything_that_is_not_whole_minutes(value):
    with pytest.raises(ValueError, match="whole number of minutes"):
        parse_minutes(value)


def test_missing_cook_time_means_not_cookable_not_free():
    times = CookTimes({1: 25, 2: 0})
    assert times.minutes_for(1) == 25
    # An item that can be cooked instantly is not the same as one that cannot be cooked.
    assert times.minutes_for(2) == 0
    assert times.minutes_for(99) is None


def test_cookable_is_quickest_first_and_skips_unknown_items():
    times = CookTimes({1: 40, 2: 10, 3: 10})
    assert times.cookable([3, 99, 1, 2]) == [(2, 10), (3, 10), (1, 40)]
    assert times.quickest([99, 1, 2]) == 10
    assert times.quickest([99]) is None


def test_bad_cook_time_fails_at_construction():
    with pytest.raises(ValueError, match="Cook time for item 7"):
        CookTimes({7: -3})


def test_daily_minutes_accepts_a_flat_number_a_date_or_a_weekday():
    days = [(MON, "Mon"), (TUE, "Tue")]
    assert daily_minutes(30, days) == {MON: 30, TUE: 30}
    assert daily_minutes({"Mon": 15}, days, default=5) == {MON: 15, TUE: 5}
    assert daily_minutes(None, days, default=5) == {MON: 5, TUE: 5}
    # A specific date is more deliberate than a standing weekday rule, so it wins.
    assert daily_minutes({MON: 90, "Mon": 15}, days) == {MON: 90, TUE: 0}


def test_no_time_free_means_everything_is_ordered():
    slots = [(MON, 1), (MON, 3)]
    decision = plan_cook_or_order(slots, {(MON, 1): 10, (MON, 3): 20}, {MON: 0})
    assert decision == {(MON, 1): ORDER, (MON, 3): ORDER}
    assert order_days(decision) == [MON]
    assert cook_days(decision) == []


def test_quickest_first_buys_the_most_cooked_meals():
    slots = [(MON, 1), (MON, 2), (MON, 3)]
    cook = {(MON, 1): 45, (MON, 2): 10, (MON, 3): 15}
    # 30 minutes fits lunch and dinner (25 min) but never breakfast's 45.
    decision = plan_cook_or_order(slots, cook, {MON: 30})
    assert decision == {(MON, 1): ORDER, (MON, 2): COOK, (MON, 3): COOK}


def test_a_slot_with_nothing_cookable_is_ordered_and_costs_no_time():
    slots = [(MON, 1), (MON, 3)]
    # Breakfast has no cookable candidate; its absence must not consume the hour.
    decision = plan_cook_or_order(slots, {(MON, 3): 50}, {MON: 60})
    assert decision == {(MON, 1): ORDER, (MON, 3): COOK}


def test_time_does_not_leak_between_days():
    slots = [(MON, 3), (TUE, 3)]
    cook = {(MON, 3): 30, (TUE, 3): 30}
    decision = plan_cook_or_order(slots, cook, {MON: 60, TUE: 20})
    assert decision == {(MON, 3): COOK, (TUE, 3): ORDER}
    assert cook_days(decision) == [MON]
    assert order_days(decision) == [TUE]


def test_a_day_the_schedule_never_mentions_has_no_time():
    decision = plan_cook_or_order([(TUE, 3)], {(TUE, 3): 5}, {MON: 600})
    assert decision == {(TUE, 3): ORDER}


def test_pinned_cook_takes_the_time_before_anything_chosen_for_you():
    slots = [(MON, 1), (MON, 3)]
    cook = {(MON, 1): 10, (MON, 3): 45}
    # Unpinned, the quickest-first rule would cook breakfast and skip dinner.
    assert plan_cook_or_order(slots, cook, {MON: 50}) == {(MON, 1): COOK, (MON, 3): ORDER}
    # Pinning dinner reverses that: it is served first and leaves too little for breakfast.
    decision = plan_cook_or_order(slots, cook, {MON: 50}, must_cook=[(MON, 3)])
    assert decision == {(MON, 1): ORDER, (MON, 3): COOK}


def test_pinned_order_is_never_cooked_and_frees_its_time():
    slots = [(MON, 1), (MON, 3)]
    cook = {(MON, 1): 20, (MON, 3): 20}
    decision = plan_cook_or_order(slots, cook, {MON: 20}, must_order=[(MON, 1)])
    assert decision == {(MON, 1): ORDER, (MON, 3): COOK}


def test_pinned_cook_that_does_not_fit_is_refused_with_the_numbers():
    with pytest.raises(ScheduleInfeasibleError, match="needs 90 min to cook but 30 min are free"):
        plan_cook_or_order([(MON, 3)], {(MON, 3): 90}, {MON: 30}, must_cook=[(MON, 3)])


def test_pinned_cook_with_nothing_cookable_is_refused():
    with pytest.raises(ScheduleInfeasibleError, match="nothing cookable"):
        plan_cook_or_order([(MON, 3)], {}, {MON: 600}, must_cook=[(MON, 3)])


def test_pinning_a_slot_both_ways_is_refused():
    with pytest.raises(ScheduleInfeasibleError, match="both cooked and ordered"):
        plan_cook_or_order(
            [(MON, 3)], {(MON, 3): 5}, {MON: 60}, must_cook=[(MON, 3)], must_order=[(MON, 3)]
        )


def test_every_slot_is_decided_even_with_no_cook_times_at_all():
    slots = [(MON, 1), (MON, 2), (TUE, 3)]
    decision = plan_cook_or_order(slots, {}, {})
    assert sorted(decision) == sorted(slots)
    assert set(decision.values()) == {ORDER}


def test_the_greedy_order_cooks_as_many_meals_as_any_other_choice_could():
    """The rule claims to maximise cooked meals per day; check it against brute force."""
    import itertools

    cook = {(MON, 1): 25, (MON, 2): 10, (MON, 3): 15, (MON, 4): 30}
    slots = list(cook)
    for budget in range(0, 85, 5):
        decision = plan_cook_or_order(slots, cook, {MON: budget})
        chosen = sum(1 for choice in decision.values() if choice == COOK)
        best = max(
            len(combo)
            for size in range(len(slots) + 1)
            for combo in itertools.combinations(slots, size)
            if sum(cook[slot] for slot in combo) <= budget
        )
        assert chosen == best, f"budget {budget}: cooked {chosen}, best possible {best}"
