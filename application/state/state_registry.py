"""Planner-facing registry for interpreted execution state."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional


class StateRegistry:
    """Stores normalized step outcomes for recovery, parameter reuse, and replanning."""

    def __init__(self):
        self._steps: Dict[str, Dict[str, Any]] = {}

    def record_step(
        self,
        *,
        step_id: str,
        tool_name: str,
        operation: str,
        status: str,
        output: Any = None,
        error: Optional[str] = None,
        artifacts: Optional[List[Dict[str, Any]]] = None,
        feedback: Optional[Dict[str, Any]] = None,
        planner_signal: Optional[Dict[str, Any]] = None,
        resolved_parameters: Optional[Dict[str, Any]] = None,
        execution_time: Optional[float] = None,
    ) -> None:
        self._steps[step_id] = {
            "step_id": step_id,
            "tool_name": tool_name,
            "operation": operation,
            "status": status,
            "output": output,
            "error": error,
            "artifacts": list(artifacts or []),
            "feedback": dict(feedback or {}),
            "planner_signal": dict(planner_signal or {}),
            "resolved_parameters": dict(resolved_parameters or {}),
            "execution_time": execution_time,
            "updated_at": datetime.now().isoformat(),
        }

    def get_step_output(self, step_id: str) -> Any:
        record = self._steps.get(step_id, {})
        return record.get("output")

    def get_step_record(self, step_id: str) -> Dict[str, Any]:
        return dict(self._steps.get(step_id, {}))

    def build_completed_summary(self, max_chars: int = 400) -> Dict[str, Any]:
        summary: Dict[str, Any] = {}
        for step_id, record in self._steps.items():
            if record.get("status") != "completed":
                continue
            planner_signal = record.get("planner_signal") or {}
            text = planner_signal.get("output_summary") or self._stringify(record.get("output"))
            summary[step_id] = text[:max_chars] + ("..." if len(text) > max_chars else "")
        return summary

    def build_completed_artifacts(self, max_chars: int = 4000) -> Dict[str, Dict[str, Any]]:
        artifacts: Dict[str, Dict[str, Any]] = {}
        for step_id, record in self._steps.items():
            if record.get("status") != "completed":
                continue
            output = record.get("output")
            if output is None:
                continue
            artifacts[step_id] = self._serialize_output(output, max_chars=max_chars)
        return artifacts

    def latest_world_state(self) -> Dict[str, Any]:
        world_state: Dict[str, Any] = {}
        for record in self._steps.values():
            feedback = record.get("feedback") or {}
            step_world_state = feedback.get("world_state")
            if isinstance(step_world_state, dict):
                world_state.update(step_world_state)
        return world_state

    def build_planner_context(self) -> Dict[str, Any]:
        return {
            "completed_summary": self.build_completed_summary(),
            "completed_artifacts": self.build_completed_artifacts(),
            "latest_world_state": self.latest_world_state(),
        }

    def build_tool_history(self) -> List[Dict[str, Any]]:
        """Return canonical tool usage history for UI, learning, and analytics."""
        history: List[Dict[str, Any]] = []
        for step_id, record in self._steps.items():
            history.append({
                "step_id": step_id,
                "tool": record.get("tool_name"),
                "operation": record.get("operation"),
                "success": record.get("status") == "completed",
                "data": record.get("output"),
                "error": record.get("error"),
                "execution_time": record.get("execution_time") or 0.0,
            })
        return history

    def build_completed_steps(self) -> List[Dict[str, Any]]:
        """Return compact completed-step records for local policy/recovery decisions."""
        steps: List[Dict[str, Any]] = []
        for record in self._steps.values():
            if record.get("status") != "completed":
                continue
            steps.append({
                "tool": record.get("tool_name"),
                "operation": record.get("operation"),
                "parameters": dict(record.get("resolved_parameters") or {}),
                "output": record.get("output"),
            })
        return steps

    def _serialize_output(self, output: Any, max_chars: int = 4000) -> Dict[str, Any]:
        try:
            if isinstance(output, (dict, list)):
                text = json.dumps(output, default=str)
                truncated = len(text) > max_chars
                return {
                    "kind": "structured",
                    "output": text[:max_chars] + ("..." if truncated else ""),
                    "truncated": truncated,
                }
            text = str(output)
            truncated = len(text) > max_chars
            kind = "text" if isinstance(output, str) else "scalar"
            return {
                "kind": kind,
                "output": text[:max_chars] + ("..." if truncated else ""),
                "truncated": truncated,
            }
        except Exception:
            return {
                "kind": "text",
                "output": str(output)[:max_chars],
                "truncated": True,
            }

    def _stringify(self, value: Any) -> str:
        try:
            if isinstance(value, (dict, list)):
                return json.dumps(value, default=str)
            return str(value)
        except Exception:
            return str(value)
