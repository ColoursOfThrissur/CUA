"""Shared desktop automation failure taxonomy."""

from __future__ import annotations


def classify_desktop_failure(error_type: str, message: str = "") -> str:
    """Map low-level tool failures to planner-visible desktop categories."""
    upper = str(error_type or "").strip().upper()
    lower = str(message or "").strip().lower()

    if upper in {
        "TIMEOUT",
        "WINDOW_NOT_FOCUSED",
        "WINDOW_NOT_ACTIVE",
        "WAIT_TIMEOUT",
        "NOT_READY",
    }:
        return "TIMING_ISSUE"

    if upper in {
        "ELEMENT_NOT_FOUND",
        "TARGET_NOT_FOUND",
        "WINDOW_NOT_FOUND",
        "OUT_OF_BOUNDS",
        "SMART_CLICK_FAILED",
        "SMART_FOCUS_FAILED",
        "LOCATE_FAILED",
        "STATE_INFERENCE_FAILED",
    }:
        return "ENVIRONMENT_CHANGED"

    if any(fragment in lower for fragment in ("timeout", "loading", "not ready", "still launching")):
        return "TIMING_ISSUE"

    if any(fragment in lower for fragment in ("not found", "no window", "out of bounds", "not visible", "environment changed")):
        return "ENVIRONMENT_CHANGED"

    return "NO_EFFECT"
