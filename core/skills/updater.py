from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class SkillUpdatePlan:
    skill_name: str
    tool_name: str
    action: str
    operations: List[str]
    output_types: List[str]
    note: str
    workflow_updates: List[str]
    gap_type: Optional[str] = None
    suggested_action: Optional[str] = None
    reasons: Optional[List[str]] = None
    example_tasks: Optional[List[str]] = None
    example_errors: Optional[List[str]] = None


class SkillUpdater:
    def __init__(self, skills_root: str = "skills"):
        self.skills_root = Path(skills_root)

    def plan_tool_creation_update(
        self,
        skill_name: str,
        tool_name: str,
        operations: Optional[List[str]] = None,
        output_types: Optional[List[str]] = None,
        gap_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not skill_name:
            return None

        workflow_updates = self._build_workflow_updates(
            tool_name=tool_name,
            action="create_tool",
            operations=operations or [],
            gap_context=gap_context,
        )
        plan = SkillUpdatePlan(
            skill_name=skill_name,
            tool_name=tool_name,
            action="create_tool",
            operations=operations or [],
            output_types=output_types or [],
            note=self._build_note("Added", tool_name, operations or []),
            workflow_updates=workflow_updates,
            gap_type=(gap_context or {}).get("gap_type"),
            suggested_action=(gap_context or {}).get("suggested_action"),
            reasons=list((gap_context or {}).get("reasons") or []),
            example_tasks=list((gap_context or {}).get("example_tasks") or []),
            example_errors=list((gap_context or {}).get("example_errors") or []),
        )
        return self._as_dict(plan)

    def plan_tool_evolution_updates(
        self,
        tool_name: str,
        operations: Optional[List[str]] = None,
        gap_context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        updates: List[Dict[str, Any]] = []
        for skill_name in self.find_skills_for_tool(tool_name):
            workflow_updates = self._build_workflow_updates(
                tool_name=tool_name,
                action="evolve_tool",
                operations=operations or [],
                gap_context=gap_context,
            )
            plan = SkillUpdatePlan(
                skill_name=skill_name,
                tool_name=tool_name,
                action="evolve_tool",
                operations=operations or [],
                output_types=[],
                note=self._build_note("Updated", tool_name, operations or []),
                workflow_updates=workflow_updates,
                gap_type=(gap_context or {}).get("gap_type"),
                suggested_action=(gap_context or {}).get("suggested_action"),
                reasons=list((gap_context or {}).get("reasons") or []),
                example_tasks=list((gap_context or {}).get("example_tasks") or []),
                example_errors=list((gap_context or {}).get("example_errors") or []),
            )
            updates.append(self._as_dict(plan))
        return updates

    def apply_update_plan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        skill_name = str(plan.get("skill_name") or "").strip()
        tool_name = str(plan.get("tool_name") or "").strip()
        if not skill_name or not tool_name:
            return {"success": False, "error": "skill_name and tool_name are required"}

        skill_dir = self.skills_root / skill_name
        json_path = skill_dir / "skill.json"
        md_path = skill_dir / "SKILL.md"
        if not json_path.exists() or not md_path.exists():
            return {"success": False, "error": f"Skill assets not found for {skill_name}"}

        data = json.loads(json_path.read_text(encoding="utf-8"))
        preferred_tools = list(data.get("preferred_tools") or [])
        if tool_name not in preferred_tools:
            preferred_tools.append(tool_name)
        data["preferred_tools"] = preferred_tools

        for output_type in plan.get("output_types") or []:
            if output_type not in data.get("output_types", []):
                data.setdefault("output_types", []).append(output_type)

        json_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

        note = str(plan.get("note") or "").strip()
        if note:
            self._append_note(md_path, note)
        self._apply_workflow_updates(md_path, plan)

        return {
            "success": True,
            "skill_name": skill_name,
            "tool_name": tool_name,
            "action": plan.get("action"),
        }

    def apply_update_plans(self, plans: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results = []
        for plan in plans or []:
            results.append(self.apply_update_plan(plan))
        return results

    def find_skills_for_tool(self, tool_name: str) -> List[str]:
        matches = []
        for skill_dir in self.skills_root.iterdir():
            if not skill_dir.is_dir():
                continue
            json_path = skill_dir / "skill.json"
            if not json_path.exists():
                continue
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            known_tools = list(data.get("preferred_tools") or []) + list(data.get("required_tools") or [])
            if tool_name in known_tools:
                matches.append(skill_dir.name)
        return matches

    def _append_note(self, md_path: Path, note: str) -> None:
        content = md_path.read_text(encoding="utf-8")
        marker = "## Managed Tool Updates"
        entry = f"- {note}"
        if entry in content:
            return
        if marker not in content:
            if not content.endswith("\n"):
                content += "\n"
            content += f"\n{marker}\n{entry}\n"
        else:
            content += f"{entry}\n"
        md_path.write_text(content, encoding="utf-8")

    def _apply_workflow_updates(self, md_path: Path, plan: Dict[str, Any]) -> None:
        updates = [str(item).strip() for item in (plan.get("workflow_updates") or []) if str(item).strip()]
        if not updates:
            return

        content = md_path.read_text(encoding="utf-8")
        marker = "## Managed Workflow Updates"
        header = self._workflow_header(plan)
        block_lines = [f"### {header}"]
        for reason in plan.get("reasons") or []:
            block_lines.append(f"- Reason: {reason}")
        for example_task in plan.get("example_tasks") or []:
            block_lines.append(f"- Example request: `{example_task}`")
        for example_error in plan.get("example_errors") or []:
            block_lines.append(f"- Observed failure: `{example_error}`")
        for item in updates:
            block_lines.append(f"- {item}")
        block = "\n".join(block_lines)
        if block in content:
            return

        if marker not in content:
            if not content.endswith("\n"):
                content += "\n"
            content += f"\n{marker}\n{block}\n"
        else:
            content += f"\n{block}\n"
        md_path.write_text(content, encoding="utf-8")

    def _build_note(self, verb: str, tool_name: str, operations: List[str]) -> str:
        operation_text = ", ".join(operations[:4]) if operations else "new workflow support"
        return f"{verb} `{tool_name}` for operations: {operation_text}."

    def _build_workflow_updates(
        self,
        tool_name: str,
        action: str,
        operations: List[str],
        gap_context: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        gap_context = gap_context or {}
        updates: List[str] = []
        if action == "create_tool":
            updates.append(f"Prefer `{tool_name}` when the task needs: {', '.join(operations[:4]) or 'new capability support'}.")
        else:
            updates.append(f"Re-evaluate `{tool_name}` first for improved handling of: {', '.join(operations[:4]) or 'existing workflow steps'}.")

        gap_type = gap_context.get("gap_type") or ""
        if gap_type == "actionable_request_no_tool_call":
            updates.append("Treat direct action requests as execution-first; do not return conversational refusals when this workflow is available.")
        elif gap_type == "matched_skill_missing_workflow":
            updates.append("When routing matches this skill but the workflow is incomplete, build an explicit multi-step plan before falling back.")
        elif gap_type == "matched_skill_missing_tool":
            updates.append("If existing tools cannot satisfy the requested step, escalate to a missing-tool path instead of retrying the same workflow.")

        suggested_action = gap_context.get("suggested_action") or ""
        if suggested_action == "improve_skill_workflow":
            updates.append("Strengthen the step-by-step workflow before proposing unrelated new tools.")
        elif suggested_action == "improve_skill_routing":
            updates.append("Bias routing toward this skill when the user request is action-oriented and matches the trigger patterns.")

        return list(dict.fromkeys(updates))

    def _workflow_header(self, plan: Dict[str, Any]) -> str:
        label = plan.get("action") or "update"
        tool_name = plan.get("tool_name") or "tool"
        gap_type = plan.get("gap_type")
        if gap_type:
            return f"{tool_name} ({label}, {gap_type})"
        return f"{tool_name} ({label})"

    def _as_dict(self, plan: SkillUpdatePlan) -> Dict[str, Any]:
        return {
            "skill_name": plan.skill_name,
            "tool_name": plan.tool_name,
            "action": plan.action,
            "operations": plan.operations,
            "output_types": plan.output_types,
            "note": plan.note,
            "workflow_updates": plan.workflow_updates,
            "gap_type": plan.gap_type,
            "suggested_action": plan.suggested_action,
            "reasons": plan.reasons or [],
            "example_tasks": plan.example_tasks or [],
            "example_errors": plan.example_errors or [],
        }
