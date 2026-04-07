"""Path-aware execution routing for isolated worktree plans."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

from application.services.worktree_event_service import WorktreeEventService
from application.services.worktree_task_service import WorktreeTaskService


class WorktreeExecutionService:
    """Re-root bounded repo tool parameters into a prepared worktree."""

    REPO_AWARE_TOOLS = {"FilesystemTool", "GlobTool", "GrepTool", "ShellTool"}
    PATH_KEYS = {"path", "source", "destination", "root", "working_dir", "file_path", "target_file"}
    PATH_LIST_KEYS = {"paths"}

    def apply_to_step(self, step, parameters: Dict[str, Any], plan) -> Tuple[Dict[str, Any], Dict[str, Any] | None]:
        profile = self._get_profile(plan)
        if not profile or getattr(step, "tool_name", "") not in self.REPO_AWARE_TOOLS:
            return dict(parameters or {}), None

        adjusted = dict(parameters or {})
        changed_keys = []
        tool_name = getattr(step, "tool_name", "")

        for key in list(adjusted.keys()):
            value = adjusted[key]
            if key in self.PATH_KEYS and isinstance(value, str):
                rebased = self._rebase_path(value, profile)
                if rebased != value:
                    adjusted[key] = rebased
                    changed_keys.append(key)
            elif key in self.PATH_LIST_KEYS and isinstance(value, list):
                rebased_list = [self._rebase_path(item, profile) if isinstance(item, str) else item for item in value]
                if rebased_list != value:
                    adjusted[key] = rebased_list
                    changed_keys.append(key)

        if tool_name == "ShellTool" and not str(adjusted.get("working_dir") or "").strip():
            adjusted["working_dir"] = profile["worktree_path"]
            changed_keys.append("working_dir")

        metadata = {
            "execution_mode": profile["execution_mode"],
            "worktree_label": profile["label"],
            "worktree_path": profile["worktree_path"],
            "git_root": profile["git_root"],
            "changed_keys": changed_keys,
            "tool_name": tool_name,
        }
        try:
            WorktreeTaskService.record_activity(
                profile["worktree_path"],
                activity_type="routed_step",
                details={"tool_name": tool_name, "changed_keys": changed_keys},
            )
            WorktreeEventService().record_event(
                "routed_step",
                worktree_label=profile["label"],
                worktree_path=profile["worktree_path"],
                details={"tool_name": tool_name, "changed_keys": changed_keys},
            )
        except Exception:
            pass
        return adjusted, metadata

    def _get_profile(self, plan) -> Dict[str, str] | None:
        workflow_metadata = getattr(plan, "workflow_metadata", None)
        if not isinstance(workflow_metadata, dict):
            return None
        if workflow_metadata.get("execution_mode") != "isolated_worktree":
            return None
        worktree = workflow_metadata.get("worktree")
        if not isinstance(worktree, dict):
            return None

        worktree_path_raw = str(worktree.get("worktree_path") or "").strip()
        if not worktree_path_raw:
            return None

        worktree_path = Path(worktree_path_raw).resolve()
        git_root = str(worktree.get("git_root") or "").strip()
        if not git_root:
            git_root = self._infer_git_root(worktree_path)

        return {
            "execution_mode": "isolated_worktree",
            "label": str(worktree.get("label") or worktree_path.name),
            "worktree_path": str(worktree_path),
            "git_root": str(Path(git_root).resolve()),
        }

    def _infer_git_root(self, worktree_path: Path) -> str:
        if worktree_path.parent.name == ".worktrees":
            return str(worktree_path.parent.parent.resolve())
        return str(worktree_path.parent.resolve())

    def _rebase_path(self, raw_value: str, profile: Dict[str, str]) -> str:
        value = str(raw_value or "").strip()
        if not value:
            return value

        worktree_root = Path(profile["worktree_path"]).resolve()
        git_root = Path(profile["git_root"]).resolve()

        if value in {".", "./"}:
            return str(worktree_root)

        candidate = Path(value)
        if candidate.is_absolute():
            resolved = candidate.resolve()
            if self._is_under(resolved, worktree_root):
                return str(resolved)
            if self._is_under(resolved, git_root):
                relative = resolved.relative_to(git_root)
                return str((worktree_root / relative).resolve())
            return value

        rebased = (worktree_root / candidate).resolve()
        if not self._is_under(rebased, worktree_root):
            raise ValueError(f"Isolated worktree routing blocked path escape: {value}")
        return str(rebased)

    def _is_under(self, candidate: Path, root: Path) -> bool:
        try:
            candidate.relative_to(root)
            return True
        except ValueError:
            return False
