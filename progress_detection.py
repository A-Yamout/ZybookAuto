from __future__ import annotations

from typing import Any

_COMPLETE_STRINGS = {"complete", "completed", "done", "finished", "passed", "100%"}
_BOOL_KEYS = {
    "complete",
    "completed",
    "is_complete",
    "is_completed",
    "fully_complete",
    "fully_completed",
    "all_complete",
}
_STATUS_KEYS = {"status", "state", "completion_status"}
_PERCENT_KEYS = {
    "completion_percent",
    "completion_percentage",
    "percent_complete",
    "percentage_complete",
    "percent_completed",
}
_PAIR_KEYS = (
    ("completed", "total"),
    ("completed_parts", "total_parts"),
    ("parts_completed", "parts_total"),
    ("points_earned", "points_possible"),
    ("earned_points", "possible_points"),
)
_NESTED_KEYS = {
    "progress",
    "completion",
    "user_progress",
    "student_progress",
    "activity_progress",
    "participation_progress",
    "challenge_progress",
    "score",
}


def completion_signal(value: Any) -> bool | None:
    """Return True/False only when the payload contains an explicit completion signal.

    ZyBooks has changed its response shapes over time. This intentionally recognizes
    several explicit forms while returning None when a payload is ambiguous.
    """
    if not isinstance(value, dict):
        return None

    for key in _BOOL_KEYS:
        if key in value and isinstance(value[key], bool):
            return value[key]

    for key in _STATUS_KEYS:
        raw = value.get(key)
        if isinstance(raw, str):
            normalized = raw.strip().lower()
            if normalized in _COMPLETE_STRINGS:
                return True
            if normalized in {"incomplete", "not_started", "not started", "pending", "started", "in_progress", "in progress"}:
                return False

    for key in _PERCENT_KEYS:
        raw = value.get(key)
        if isinstance(raw, (int, float)):
            return raw >= 100
        if isinstance(raw, str):
            try:
                return float(raw.rstrip("%")) >= 100
            except ValueError:
                pass

    for completed_key, total_key in _PAIR_KEYS:
        completed = value.get(completed_key)
        total = value.get(total_key)
        if isinstance(completed, (int, float)) and isinstance(total, (int, float)) and total > 0:
            return completed >= total

    parts = value.get("parts")
    if isinstance(parts, list) and parts:
        states = [completion_signal(part) for part in parts if isinstance(part, dict)]
        known = [state for state in states if state is not None]
        if known:
            return len(known) == len(states) and all(known)

    for key in _NESTED_KEYS:
        nested = value.get(key)
        if isinstance(nested, dict):
            signal = completion_signal(nested)
            if signal is not None:
                return signal

    return None


def resource_complete(resource: dict[str, Any]) -> bool:
    return completion_signal(resource) is True


def section_complete(section: dict[str, Any], resources: list[dict[str, Any]]) -> tuple[bool, str]:
    section_signal = completion_signal(section)
    if section_signal is True:
        return True, "section-level completion signal"

    if resources:
        states = [completion_signal(resource) for resource in resources]
        known_states = [state for state in states if state is not None]
        if known_states and len(known_states) == len(resources) and all(known_states):
            return True, "all activity resources report complete"

    return False, "no explicit complete signal found"
