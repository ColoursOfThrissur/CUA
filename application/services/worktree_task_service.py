"""Create and manage bounded git worktrees for isolated coding tasks."""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from application.services.worktree_event_service import WorktreeEventService
from application.services.worktree_isolation_service import WorktreeIsolationService


class WorktreeTaskService:
    """Provision isolated worktree directories for bounded tasks."""

    METADATA_FILENAME = ".forge-worktree.json"

    def __init__(self, repo_path: str = ".") -> None:
        self.repo_path = Path(repo_path)
        self.readiness = WorktreeIsolationService(repo_path)
        self.events = WorktreeEventService()

    def derive_label(self, raw_label: str) -> str:
        return self._sanitize_label(raw_label)

    def create_worktree(self, label: str) -> Dict[str, Any]:
        readiness = self.readiness.get_readiness()
        if not readiness.get("ready"):
            return {
                "success": False,
                "error": "worktree_not_ready",
                "reason": readiness.get("reason", "Repository is not ready for worktree isolation."),
                "readiness": readiness,
            }

        sanitized = self._sanitize_label(label)
        if not sanitized:
            return {
                "success": False,
                "error": "invalid_label",
                "reason": "Provide a short label containing letters, numbers, dash, or underscore.",
                "readiness": readiness,
            }

        git_root = Path(str(readiness["git_root"]))
        worktree_root = self._worktree_root(git_root)
        worktree_root.mkdir(parents=True, exist_ok=True)
        try:
            worktree_path = self._resolve_managed_path(worktree_root, sanitized)
        except ValueError as exc:
            return {
                "success": False,
                "error": "unsafe_path",
                "reason": str(exc),
                "readiness": readiness,
            }
        if worktree_path.exists():
            return {
                "success": False,
                "error": "already_exists",
                "reason": f"Worktree path already exists: {worktree_path}",
                "readiness": readiness,
            }

        base_branch = str(readiness.get("branch") or "main")
        branch_name = f"forge/{sanitized}"
        branch_exists = bool(self._run_git(["branch", "--list", branch_name]).strip())
        if branch_exists:
            self._run_git(["worktree", "add", str(worktree_path), branch_name], cwd=git_root)
        else:
            self._run_git(["worktree", "add", "-b", branch_name, str(worktree_path), base_branch], cwd=git_root)

        metadata = {
            "version": 1,
            "label": sanitized,
            "branch_name": branch_name,
            "base_branch": base_branch,
            "git_root": str(git_root),
            "worktree_path": str(worktree_path),
            "created_at": self._now_iso(),
            "last_activity_at": self._now_iso(),
            "last_routed_at": None,
            "last_command_at": None,
        }
        self._write_metadata(worktree_path, metadata)
        self.events.record_event(
            "created",
            worktree_label=sanitized,
            worktree_path=str(worktree_path),
            details={
                "branch_name": branch_name,
                "base_branch": base_branch,
                "branch_exists": branch_exists,
            },
        )

        return {
            "success": True,
            "label": sanitized,
            "branch_name": branch_name,
            "base_branch": base_branch,
            "git_root": str(git_root),
            "worktree_path": str(worktree_path),
            "branch_exists": branch_exists,
            "metadata": metadata,
        }

    def list_worktrees(self) -> Dict[str, Any]:
        readiness = self.readiness.get_readiness()
        if not readiness.get("git_root"):
            return {
                "success": False,
                "error": "worktree_unavailable",
                "reason": readiness.get("reason", "Worktree inspection is unavailable."),
                "readiness": readiness,
                "worktrees": [],
            }

        git_root = Path(str(readiness["git_root"]))
        worktree_root = self._worktree_root(git_root)
        worktrees = self._parse_worktree_list(
            self._run_git(["worktree", "list", "--porcelain"], cwd=git_root),
            worktree_root=worktree_root,
        )
        return {
            "success": True,
            "ready": readiness.get("ready", False),
            "readiness": readiness,
            "worktrees": worktrees,
            "managed_count": sum(1 for item in worktrees if item.get("managed")),
            "cleanup_candidate_count": sum(
                1
                for item in worktrees
                if (item.get("cleanup_recommendation") or {}).get("action") in {"review_cleanup", "remove_now", "prune_entry"}
            ),
        }

    def remove_worktree(self, label_or_path: str, force: bool = False) -> Dict[str, Any]:
        readiness = self.readiness.get_readiness()
        if not readiness.get("git_root"):
            return {
                "success": False,
                "error": "worktree_unavailable",
                "reason": readiness.get("reason", "Worktree removal is unavailable."),
                "readiness": readiness,
            }

        target_name = self._sanitize_label(label_or_path)
        if not target_name:
            return {
                "success": False,
                "error": "invalid_label",
                "reason": "Provide a worktree label containing letters, numbers, dash, or underscore.",
                "readiness": readiness,
            }

        git_root = Path(str(readiness["git_root"]))
        worktree_root = self._worktree_root(git_root)
        worktree_path = self._resolve_managed_path(worktree_root, target_name)
        if not worktree_path.exists():
            return {
                "success": False,
                "error": "not_found",
                "reason": f"Managed worktree was not found: {worktree_path}",
                "readiness": readiness,
            }

        status_lines = self._status_lines(worktree_path)
        if status_lines and not force:
            return {
                "success": False,
                "error": "dirty_worktree",
                "reason": "Worktree has uncommitted changes. Re-run with force to remove it.",
                "worktree_path": str(worktree_path),
                "changed_files": status_lines[:20],
                "readiness": readiness,
            }

        args = ["worktree", "remove"]
        if force:
            args.append("--force")
        args.append(str(worktree_path))
        self._run_git(args, cwd=git_root)
        self._run_git(["worktree", "prune"], cwd=git_root)
        self.events.record_event(
            "removed",
            worktree_label=target_name,
            worktree_path=str(worktree_path),
            details={
                "force": force,
                "changed_files_removed": status_lines[:20],
            },
        )

        return {
            "success": True,
            "label": target_name,
            "worktree_path": str(worktree_path),
            "force": force,
            "changed_files_removed": status_lines[:20],
            "branch_preserved": True,
        }

    def cleanup_worktrees(self, apply: bool = False) -> Dict[str, Any]:
        listed = self.list_worktrees()
        if not listed.get("success"):
            return listed

        candidates = []
        actions = {"review_cleanup", "remove_now", "prune_entry"}
        for item in listed.get("worktrees", []):
            cleanup = item.get("cleanup_recommendation") or {}
            if not item.get("managed"):
                continue
            if item.get("dirty") or item.get("locked"):
                continue
            if cleanup.get("action") not in actions:
                continue
            candidates.append(item)

        report = {
            "success": True,
            "mode": "apply" if apply else "preview",
            "candidate_count": len(candidates),
            "candidate_labels": [item.get("label") or Path(str(item.get("path") or "")).name for item in candidates],
            "candidates": candidates,
            "removed": [],
            "failed": [],
        }

        self.events.record_event(
            "cleanup_preview" if not apply else "cleanup_apply_started",
            details={
                "candidate_count": report["candidate_count"],
                "candidate_labels": report["candidate_labels"],
            },
        )

        if not apply:
            return report

        for item in candidates:
            label = str(item.get("label") or "").strip()
            try:
                removed = self.remove_worktree(label, force=False)
            except Exception as exc:
                report["failed"].append({"label": label, "reason": str(exc)})
                continue
            if removed.get("success"):
                report["removed"].append(removed)
            else:
                report["failed"].append({"label": label, "reason": removed.get("reason", "cleanup failed")})

        report["removed_count"] = len(report["removed"])
        report["failed_count"] = len(report["failed"])
        self.events.record_event(
            "cleanup_applied",
            details={
                "removed_count": report["removed_count"],
                "failed_count": report["failed_count"],
                "candidate_labels": report["candidate_labels"],
            },
        )
        return report

    @classmethod
    def record_activity(
        cls, worktree_path: str | Path, *, activity_type: str = "routed_step", details: Optional[Dict[str, Any]] = None
    ) -> None:
        path = Path(str(worktree_path)).resolve()
        metadata = cls._read_metadata(path) or {
            "version": 1,
            "label": path.name,
            "worktree_path": str(path),
            "created_at": cls._now_iso(),
        }
        now = cls._now_iso()
        metadata["last_activity_at"] = now
        metadata["last_routed_at"] = now if activity_type == "routed_step" else metadata.get("last_routed_at")
        metadata["last_command_at"] = now if activity_type == "command" else metadata.get("last_command_at")
        metadata["last_activity_type"] = activity_type
        if details:
            metadata["last_activity_details"] = details
        cls._write_metadata(path, metadata)
        WorktreeEventService().record_event(
            "activity_recorded",
            worktree_label=str(metadata.get("label") or path.name),
            worktree_path=str(path),
            details={"activity_type": activity_type, **(details or {})},
        )

    def _sanitize_label(self, label: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(label or "").strip().lower()).strip("-_")
        return normalized[:48]

    def _worktree_root(self, git_root: Path) -> Path:
        return (git_root / ".worktrees").resolve()

    def _resolve_managed_path(self, worktree_root: Path, sanitized: str) -> Path:
        worktree_path = (worktree_root / sanitized).resolve()
        if worktree_root not in worktree_path.parents and worktree_path != worktree_root:
            raise ValueError("Resolved worktree path escaped the allowed workspace root.")
        return worktree_path

    def _parse_worktree_list(self, text: str, *, worktree_root: Path) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        current: Dict[str, Any] = {}
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                if current:
                    entries.append(self._finalize_worktree_entry(current, worktree_root))
                    current = {}
                continue
            key, _, value = stripped.partition(" ")
            current[key] = value.strip()
        if current:
            entries.append(self._finalize_worktree_entry(current, worktree_root))
        return entries

    def _finalize_worktree_entry(self, entry: Dict[str, Any], worktree_root: Path) -> Dict[str, Any]:
        path_value = str(entry.get("worktree") or "").strip()
        path = Path(path_value).resolve() if path_value else None
        managed = bool(path and (path == worktree_root or worktree_root in path.parents))
        label = path.name if managed and path else ""
        branch = str(entry.get("branch") or "").replace("refs/heads/", "")
        status_lines = self._status_lines(path) if path and path.exists() else []
        metadata = self._read_metadata(path) if path and managed and path.exists() else None
        derived = self._derive_lifecycle(path, metadata)
        cleanup_recommendation = self._build_cleanup_recommendation(
            dirty=bool(status_lines),
            locked="locked" in entry,
            prunable="prunable" in entry,
            age_hours=derived.get("age_hours"),
            idle_hours=derived.get("idle_hours"),
        )
        handoff = dict((metadata or {}).get("handoff") or {})
        return {
            "path": str(path) if path else path_value,
            "branch": branch,
            "head": entry.get("HEAD", ""),
            "detached": "detached" in entry,
            "locked": "locked" in entry,
            "prunable": "prunable" in entry,
            "managed": managed,
            "label": label,
            "dirty": bool(status_lines),
            "changed_files": status_lines[:10],
            "created_at": derived.get("created_at"),
            "last_activity_at": derived.get("last_activity_at"),
            "last_routed_at": derived.get("last_routed_at"),
            "age_hours": derived.get("age_hours"),
            "idle_hours": derived.get("idle_hours"),
            "cleanup_recommendation": cleanup_recommendation,
            "handoff": handoff,
        }

    def _status_lines(self, worktree_path: Optional[Path]) -> List[str]:
        if not worktree_path:
            return []
        try:
            output = self._run_git(["-C", str(worktree_path), "status", "--short"], cwd=self.repo_path)
            return [line for line in output.splitlines() if line.strip()]
        except Exception:
            return []

    def _run_git(self, args: List[str], cwd: Path | None = None) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(cwd or self.repo_path),
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "git command failed").strip())
        return completed.stdout

    @classmethod
    def _metadata_path(cls, worktree_path: Path) -> Path:
        return worktree_path / cls.METADATA_FILENAME

    @classmethod
    def _write_metadata(cls, worktree_path: Path, metadata: Dict[str, Any]) -> None:
        metadata_path = cls._metadata_path(worktree_path)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def _read_metadata(cls, worktree_path: Optional[Path]) -> Optional[Dict[str, Any]]:
        if not worktree_path:
            return None
        metadata_path = cls._metadata_path(worktree_path)
        if not metadata_path.exists():
            return None
        try:
            return json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _derive_lifecycle(self, worktree_path: Optional[Path], metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        created_at = str((metadata or {}).get("created_at") or "").strip() or self._path_timestamp(worktree_path, "created")
        last_activity_at = str((metadata or {}).get("last_activity_at") or "").strip() or self._path_timestamp(
            worktree_path, "modified"
        )
        last_routed_at = str((metadata or {}).get("last_routed_at") or "").strip() or None

        return {
            "created_at": created_at or None,
            "last_activity_at": last_activity_at or None,
            "last_routed_at": last_routed_at,
            "age_hours": self._hours_since(created_at),
            "idle_hours": self._hours_since(last_activity_at),
        }

    def _build_cleanup_recommendation(
        self,
        *,
        dirty: bool,
        locked: bool,
        prunable: bool,
        age_hours: Optional[float],
        idle_hours: Optional[float],
    ) -> Dict[str, str]:
        if prunable:
            return {
                "level": "suggested",
                "action": "prune_entry",
                "reason": "Git already marked this worktree as prunable, so cleanup should be reviewed soon.",
            }
        if locked:
            return {
                "level": "keep",
                "action": "manual_review",
                "reason": "This worktree is locked and should be reviewed manually before any cleanup.",
            }
        if dirty:
            return {
                "level": "keep",
                "action": "retain_review",
                "reason": "This worktree has local changes and should be kept for review until those edits are resolved.",
            }
        if idle_hours is not None and idle_hours >= 168:
            return {
                "level": "high",
                "action": "remove_now",
                "reason": "This managed worktree has been clean and inactive for at least 7 days.",
            }
        if idle_hours is not None and idle_hours >= 72:
            return {
                "level": "suggested",
                "action": "review_cleanup",
                "reason": "This managed worktree has been inactive for at least 3 days and appears clean.",
            }
        if age_hours is not None and age_hours >= 24:
            return {
                "level": "low",
                "action": "keep_observe",
                "reason": "This worktree is aging, but cleanup is optional while it remains recently active.",
            }
        return {
            "level": "keep",
            "action": "keep_recent",
            "reason": "This worktree is recent or active enough to keep around for now.",
        }

    def _path_timestamp(self, worktree_path: Optional[Path], kind: str) -> Optional[str]:
        if not worktree_path or not worktree_path.exists():
            return None
        stat = worktree_path.stat()
        epoch = stat.st_ctime if kind == "created" else max(stat.st_mtime, stat.st_ctime)
        return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()

    def _hours_since(self, timestamp: Optional[str]) -> Optional[float]:
        if not timestamp:
            return None
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)
        return round(delta.total_seconds() / 3600, 2)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()
