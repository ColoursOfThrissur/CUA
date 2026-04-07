"""Read-only git worktree readiness checks for future isolated agent execution."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List


class WorktreeIsolationService:
    """Assess whether the current repository is a safe candidate for git worktree isolation."""

    def __init__(self, repo_path: str = ".") -> None:
        self.repo_path = Path(repo_path)

    def get_readiness(self) -> Dict[str, Any]:
        if not self._in_git_repo():
            return {
                "ready": False,
                "status": "unavailable",
                "reason": "Not inside a git repository.",
                "repo_path": str(self.repo_path.resolve()),
                "git_root": None,
                "branch": None,
                "dirty": None,
                "changed_files": [],
                "checks": [
                    {"name": "git_repo", "status": "fail", "detail": "Not inside a git repository."},
                ],
            }

        git_root = self._run_git(["rev-parse", "--show-toplevel"]).strip()
        branch = self._run_git(["branch", "--show-current"]).strip() or "detached"
        status_lines = [line for line in self._run_git(["status", "--short"]).splitlines() if line.strip()]
        dirty = bool(status_lines)

        checks: List[Dict[str, str]] = [
            {"name": "git_repo", "status": "pass", "detail": f"Git root: {git_root}"},
            {"name": "branch", "status": "pass" if branch != "detached" else "warn", "detail": f"Current branch: {branch}"},
            {
                "name": "workspace_state",
                "status": "warn" if dirty else "pass",
                "detail": f"{len(status_lines)} uncommitted path(s) present" if dirty else "Workspace is clean",
            },
        ]

        ready = branch != "detached"
        if dirty:
            ready = False

        reason = "Worktree isolation can be enabled safely." if ready else (
            "Uncommitted changes should be reviewed before creating isolated worktrees."
            if dirty
            else "Switch to a named branch before creating isolated worktrees."
        )

        return {
            "ready": ready,
            "status": "ready" if ready else "needs_attention",
            "reason": reason,
            "repo_path": str(self.repo_path.resolve()),
            "git_root": git_root,
            "branch": branch,
            "dirty": dirty,
            "changed_files": status_lines[:25],
            "checks": checks,
        }

    def _in_git_repo(self) -> bool:
        try:
            return self._run_git(["rev-parse", "--is-inside-work-tree"]).strip().lower() == "true"
        except Exception:
            return False

    def _run_git(self, args: List[str]) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(self.repo_path),
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "git command failed").strip())
        return completed.stdout
