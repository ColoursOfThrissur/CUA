"""Compatibility stub for the removed task manager subsystem."""

from __future__ import annotations


class TaskManagerStub:
    """Reports task-manager endpoints as unavailable without crashing callers."""

    unavailable_reason = (
        "Task manager is not currently wired in the refactored runtime."
    )

    def __init__(self) -> None:
        self.staging_areas = {}

    def get_status(self) -> dict:
        return {
            "available": False,
            "active": False,
            "parent_task": None,
            "reason": self.unavailable_reason,
        }

    def get_history(self, limit: int = 20) -> list:
        return []

    def abort_parent_task(self, parent_id: str) -> dict:
        return {
            "success": False,
            "error": self.unavailable_reason,
            "parent_id": parent_id,
        }
