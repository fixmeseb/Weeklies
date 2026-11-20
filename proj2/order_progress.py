"""Customer-facing order progress (UC13 extension).

Maps the single `status` column on "Order" onto the lifecycle stages so the
profile page can draw a stepper instead of one status word.

Lifecycle (driven by the restaurant routes in Flask_app.py):
    Ordered -> Accepted -> Preparing -> Ready -> Delivered
Cancelled is a side-exit reachable from Ordered/Accepted/Preparing.

Each status change is recorded with its time in the "OrderStatus" table
(proj2/ordering.py). Given that history, every stage shows when it was reached, and a
Cancelled order shows the stages it got through before it was cancelled. Without it
(orders from before the table existed carry only their status then), a Cancelled
order shows every stage as "cancelled" rather than guessing.
"""

STAGES = [
    ("ordered", "Ordered"),
    ("accepted", "Accepted"),
    ("preparing", "Preparing"),
    ("ready", "Ready"),
    ("delivered", "Delivered"),
]

_STAGE_INDEX = {key: i for i, (key, _label) in enumerate(STAGES)}

# Accept the US spelling too, in case it is ever written by hand or a seed script.
_ALIASES = {"canceled": "cancelled"}


def normalize_status(status):
    """
    Normalize a raw status value to a lowercase key.
    Args:
        status: Raw value from the "Order".status column (may be None).
    Returns:
        str: Lowercase, trimmed key ("" for None/blank).
    """
    if status is None:
        return ""
    key = str(status).strip().lower()
    return _ALIASES.get(key, key)


def _when(at) -> str:
    """An ISO timestamp as "Nov 19, 7:30 pm" ("" if it cannot be read)."""
    import datetime

    try:
        moment = datetime.datetime.fromisoformat(str(at))
    except (TypeError, ValueError):
        return ""
    hour = moment.hour % 12 or 12
    minutes = f":{moment.minute:02d}" if moment.minute else ""
    return f"{moment.strftime('%b')} {moment.day}, {hour}{minutes} {'am' if moment.hour < 12 else 'pm'}"


def _reached(history) -> dict:
    """stage key -> when it was last reached, from [(status, at)] oldest first."""
    reached = {}
    for status, at in history or []:
        key = normalize_status(status)
        if key in _STAGE_INDEX or key == "cancelled":
            reached[key] = _when(at)
    return reached


def order_progress(status, history=None):
    """
    Build the stepper view model for one order.
    Args:
        status: Raw value from the "Order".status column (may be None/unknown).
        history: [(status, at ISO string)] oldest first, from proj2.ordering.status_history;
            None or empty when nothing was recorded.
    Returns:
        dict: {
            "key": normalized status key, or "unknown",
            "label": text for the status badge,
            "known": False when the status is not part of the lifecycle,
            "cancelled": True for Cancelled orders,
            "cancelled_at": when it was cancelled ("" if not recorded),
            "percent": 0-100 progress through the lifecycle,
            "steps": [{"key", "label", "state", "at"}] where state is
                     "done" | "current" | "upcoming" | "cancelled" and at is when the
                     stage was reached ("" if not reached or not recorded),
        }
    """
    key = normalize_status(status)
    reached = _reached(history)
    if key == "cancelled":
        # The stages the order got through before it was cancelled, if recorded.
        got_to = max((_STAGE_INDEX[k] for k in reached if k in _STAGE_INDEX), default=-1)
        steps = []
        for i, (k, lbl) in enumerate(STAGES):
            done = i <= got_to
            steps.append(
                {
                    "key": k,
                    "label": lbl,
                    "state": "done" if done else "cancelled",
                    "at": reached.get(k, "") if done else "",
                }
            )
        return {
            "key": "cancelled",
            "label": "Cancelled",
            "known": True,
            "cancelled": True,
            "cancelled_at": reached.get("cancelled", ""),
            "percent": 0,
            "steps": steps,
        }
    if key in _STAGE_INDEX:
        current = _STAGE_INDEX[key]
        steps = []
        for i, (k, lbl) in enumerate(STAGES):
            if i < current:
                state = "done"
            elif i == current:
                state = "current"
            else:
                state = "upcoming"
            steps.append(
                {
                    "key": k,
                    "label": lbl,
                    "state": state,
                    "at": reached.get(k, "") if i <= current else "",
                }
            )
        return {
            "key": key,
            "label": STAGES[current][1],
            "known": True,
            "cancelled": False,
            "cancelled_at": "",
            "percent": round(100 * current / (len(STAGES) - 1)),
            "steps": steps,
        }

    # Unknown, blank or NULL status: degrade to a neutral badge, no stepper position.
    raw = "" if status is None else str(status).strip()
    return {
        "key": "unknown",
        "label": raw or "Unknown",
        "known": False,
        "cancelled": False,
        "cancelled_at": "",
        "percent": 0,
        "steps": [{"key": k, "label": lbl, "state": "upcoming", "at": ""} for k, lbl in STAGES],
    }
