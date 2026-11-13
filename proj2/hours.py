"""
Restaurant opening hours as people read them.

Restaurant.hours holds either per-day JSON, which the planner reads
(proj2.plan_rules.is_restaurant_open), or older free text such as
"11:00 AM - 10:00 PM". format_hours turns the JSON into a short summary that groups
days with the same times, and tidies free text without changing what it says:

    {"Mon": [1100, 2130], ..., "Sun": [1100, 2130]}  ->  "Daily 11 am–9:30 pm"
    {"Mon": [600, 1500], ..., "Sat": [], "Sun": []}   ->  "Mon–Fri 6 am–3 pm · Sat, Sun closed"
    {"Mon": [1100, 1400, 1700, 2200], ...}            ->  "Mon 11 am–2 pm, 5–10 pm · ..."
"""

import json
import re

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
GROUP_SEPARATOR = " · "


def format_time(hhmm: int) -> str:
    """1100 -> "11 am", 2130 -> "9:30 pm", 0 -> "12 am", 1200 -> "12 pm"."""
    hours, minutes = divmod(int(hhmm), 100)
    hours %= 24
    suffix = "am" if hours < 12 else "pm"
    clock = hours % 12 or 12
    return f"{clock}:{minutes:02d} {suffix}" if minutes else f"{clock} {suffix}"


def _format_window(start: int, end: int) -> str:
    opens, closes = format_time(start), format_time(end)
    # "5–10 pm" rather than "5 pm–10 pm" when both ends share am/pm
    if opens[-2:] == closes[-2:]:
        opens = opens[:-3]
    return f"{opens}–{closes}"


def _day_windows(value):
    """A day's [open, close, open, close, ...] list as a tuple of pairs; None if malformed."""
    if value is None or value == []:
        return ()
    if (
        not isinstance(value, list)
        or len(value) % 2
        or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)
    ):
        return None
    return tuple((int(value[i]), int(value[i + 1])) for i in range(0, len(value), 2))


def _day_range(first: int, last: int) -> str:
    if first == last:
        return DAYS[first]
    if last == first + 1:
        return f"{DAYS[first]}, {DAYS[last]}"
    return f"{DAYS[first]}–{DAYS[last]}"


def _format_json_hours(parsed: dict):
    week = []
    for day in DAYS:
        windows = _day_windows(parsed.get(day))
        if windows is None:
            return None
        week.append(windows)
    if not any(week):
        return "Closed"
    if all(windows == week[0] for windows in week):
        return "Daily " + ", ".join(_format_window(*w) for w in week[0])
    groups, start = [], 0
    for i in range(1, len(DAYS) + 1):
        if i == len(DAYS) or week[i] != week[start]:
            times = ", ".join(_format_window(*w) for w in week[start]) or "closed"
            groups.append(f"{_day_range(start, i - 1)} {times}")
            start = i
    return GROUP_SEPARATOR.join(groups)


def _tidy_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(
        r"(\d)\s*([AaPp])\.?\s*[Mm]\.?(?![a-z])",
        lambda m: f"{m.group(1)} {m.group(2).lower()}m",
        text,
    )
    return re.sub(r"(?<=[\dm])\s*-\s*(?=\d)", "–", text)


def format_hours(hours) -> str:
    """
    A restaurant's hours for display

    Args:
        hours (str | None): Restaurant.hours, per-day JSON or free text

    Returns:
        str: A readable summary; "" if there are no hours. JSON the planner could not
            read is shown as tidied text rather than hidden.
    """
    if hours is None:
        return ""
    text = str(hours).strip()
    if not text:
        return ""
    try:
        parsed = json.loads(text)
    except ValueError:
        return _tidy_text(text)
    if isinstance(parsed, dict) and any(day in parsed for day in DAYS):
        summary = _format_json_hours(parsed)
        if summary is not None:
            return summary
    return _tidy_text(text)
