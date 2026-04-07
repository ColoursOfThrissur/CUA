"""Policy guidance for when isolated worktree execution should be used."""
from __future__ import annotations

from typing import Any, Dict, Iterable


class WorktreePolicyService:
    """Suggest when worktree isolation is optional, suggested, or required."""

    REQUIRED_KEYWORDS = (
        "rename",
        "delete",
        "remove",
        "migrate",
        "rewrite",
        "restructure",
        "sweep",
        "repo-wide",
        "project-wide",
        "across the repo",
        "across the repository",
    )
    SUGGESTED_KEYWORDS = (
        "refactor",
        "implement",
        "fix",
        "update",
        "edit",
        "cleanup",
        "feature",
        "across",
        "workspace",
        "repository",
        "repo",
    )
    REPO_AWARE_TOOLS = {"FilesystemTool", "GlobTool", "GrepTool", "ShellTool"}

    def recommend(self, *, goal: str, plan: Any = None, readiness: Dict[str, Any] | None = None) -> Dict[str, Any]:
        goal_text = str(goal or "").strip()
        normalized = goal_text.lower()
        readiness = dict(readiness or {})

        repo_aware_steps = 0
        step_count = 0
        if plan is not None:
            for step in list(getattr(plan, "steps", []) or []):
                step_count += 1
                if getattr(step, "tool_name", "") in self.REPO_AWARE_TOOLS:
                    repo_aware_steps += 1

        level = "optional"
        mode = "inline"
        reason = "Inline execution is fine for small or low-blast-radius changes."

        if any(keyword in normalized for keyword in self.REQUIRED_KEYWORDS) or (repo_aware_steps >= 4 and step_count >= 6):
            level = "required"
            mode = "isolated_worktree"
            reason = "This plan looks destructive or broad enough that a bounded isolated worktree should be used."
        elif any(keyword in normalized for keyword in self.SUGGESTED_KEYWORDS) or repo_aware_steps >= 2 or step_count >= 4:
            level = "suggested"
            mode = "isolated_worktree"
            reason = "This plan touches enough repo-facing work that an isolated worktree would reduce risk."

        can_prepare = bool(readiness.get("ready"))
        blocked_reason = ""
        if mode == "isolated_worktree" and not can_prepare:
            blocked_reason = str(
                readiness.get("reason") or "The repository is not currently ready for isolated worktree preparation."
            )

        return {
            "level": level,
            "recommended_mode": mode,
            "reason": reason,
            "can_prepare": can_prepare,
            "blocked_reason": blocked_reason,
            "repo_aware_steps": repo_aware_steps,
            "step_count": step_count,
            "guidance": self.default_guidance(),
        }

    def default_guidance(self) -> Iterable[str]:
        return [
            "Use isolated worktrees for repo-wide refactors, renames, migrations, or destructive sweeps.",
            "Use inline execution for small targeted fixes when blast radius is clearly bounded.",
            "Keep dirty worktrees for review, and clean idle worktrees up once they have been inactive long enough.",
        ]
