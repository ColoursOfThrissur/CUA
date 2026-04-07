"""Bounded ownership handoff helpers for managed worktrees."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from application.services.worktree_event_service import WorktreeEventService
from application.services.worktree_task_service import WorktreeTaskService


class WorktreeHandoffService:
    """Assign and release explicit ownership of managed worktrees."""

    def __init__(self, repo_path: str = ".") -> None:
        self.task_service = WorktreeTaskService(repo_path=repo_path)
        self.events = WorktreeEventService()

    def list_handoffs(self) -> Dict[str, Any]:
        listed = self.task_service.list_worktrees()
        if not listed.get("success"):
            return listed
        handoffs = [
            {
                "label": item.get("label"),
                "path": item.get("path"),
                "branch": item.get("branch"),
                "dirty": item.get("dirty"),
                "handoff": item.get("handoff"),
            }
            for item in listed.get("worktrees", [])
            if item.get("managed") and item.get("handoff", {}).get("status") == "active"
        ]
        return {
            "success": True,
            "handoff_count": len(handoffs),
            "handoffs": handoffs,
        }

    def assign_handoff(
        self,
        label: str,
        *,
        owner: str,
        purpose: str = "",
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        cleanup_expectation: str = "release_or_cleanup",
        lease_hours: int = 24,
    ) -> Dict[str, Any]:
        worktree_path, metadata = self._load_managed_metadata(label)
        owner_value = str(owner or "").strip()
        if not owner_value:
            return {
                "success": False,
                "error": "missing_owner",
                "reason": "Provide an explicit owner for the worktree handoff.",
            }

        existing = metadata.get("handoff") or {}
        if existing.get("status") == "active" and existing.get("owner") != owner_value:
            return {
                "success": False,
                "error": "handoff_already_active",
                "reason": f"Worktree is already handed off to {existing.get('owner')}. Release it before reassigning.",
                "handoff": existing,
            }

        now = datetime.now(timezone.utc)
        handoff = {
            "status": "active",
            "owner": owner_value,
            "purpose": str(purpose or "").strip() or "bounded handoff",
            "assigned_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=max(1, int(lease_hours)))).isoformat(),
            "cleanup_expectation": cleanup_expectation,
            "session_id": str(session_id or "").strip() or None,
            "task_id": str(task_id or "").strip() or None,
        }
        metadata["handoff"] = handoff
        WorktreeTaskService._write_metadata(worktree_path, metadata)
        self.events.record_event(
            "handoff_assigned",
            worktree_label=metadata.get("label", label),
            worktree_path=str(worktree_path),
            session_id=handoff.get("session_id"),
            task_id=handoff.get("task_id"),
            details={
                "owner": handoff["owner"],
                "purpose": handoff["purpose"],
                "cleanup_expectation": handoff["cleanup_expectation"],
                "expires_at": handoff["expires_at"],
            },
        )
        return {
            "success": True,
            "label": metadata.get("label", label),
            "worktree_path": str(worktree_path),
            "handoff": handoff,
        }

    def release_handoff(self, label: str, *, note: str = "") -> Dict[str, Any]:
        worktree_path, metadata = self._load_managed_metadata(label)
        existing = metadata.get("handoff") or {}
        if existing.get("status") != "active":
            return {
                "success": False,
                "error": "handoff_not_active",
                "reason": "No active worktree handoff was found for this label.",
            }

        released = dict(existing)
        released["status"] = "released"
        released["released_at"] = datetime.now(timezone.utc).isoformat()
        if note:
            released["release_note"] = note
        metadata["handoff"] = released
        WorktreeTaskService._write_metadata(worktree_path, metadata)
        self.events.record_event(
            "handoff_released",
            worktree_label=metadata.get("label", label),
            worktree_path=str(worktree_path),
            session_id=released.get("session_id"),
            task_id=released.get("task_id"),
            details={
                "owner": released.get("owner"),
                "note": note,
                "cleanup_expectation": released.get("cleanup_expectation"),
            },
        )
        return {
            "success": True,
            "label": metadata.get("label", label),
            "worktree_path": str(worktree_path),
            "handoff": released,
        }

    def _load_managed_metadata(self, label: str) -> tuple[Path, Dict[str, Any]]:
        listed = self.task_service.list_worktrees()
        if not listed.get("success"):
            raise RuntimeError(listed.get("reason", "Worktree inspection unavailable."))
        normalized = self.task_service.derive_label(label)
        match = next(
            (
                item for item in listed.get("worktrees", [])
                if item.get("managed") and (item.get("label") == normalized or Path(str(item.get("path") or "")).name == normalized)
            ),
            None,
        )
        if not match:
            raise RuntimeError(f"Managed worktree was not found: {normalized}")
        worktree_path = Path(str(match["path"])).resolve()
        metadata = WorktreeTaskService._read_metadata(worktree_path) or {
            "version": 1,
            "label": normalized,
            "worktree_path": str(worktree_path),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return worktree_path, metadata
