"""Interprets raw tool output into a stable execution/planning contract."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ResultInterpretation:
    """Canonical interpretation of a tool result for execution and replanning."""
    artifacts: List[Dict[str, Any]]
    execution_feedback: Dict[str, Any]
    planner_signal: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifacts": self.artifacts,
            "execution_feedback": self.execution_feedback,
            "planner_signal": self.planner_signal,
        }


class ResultInterpreter:
    """Normalizes arbitrary tool outputs into a consistent runtime envelope."""

    def interpret(
        self,
        raw_result: Any,
        data: Any,
        success: bool,
        error: Optional[str],
        tool_name: str,
        operation: str,
    ) -> ResultInterpretation:
        artifacts = self.extract_artifacts(data)
        feedback = self.extract_execution_feedback(raw_result, data, success)
        planner_signal = self._build_planner_signal(
            tool_name=tool_name,
            operation=operation,
            data=data,
            success=success,
            error=error,
            artifacts=artifacts,
            feedback=feedback,
        )
        return ResultInterpretation(
            artifacts=artifacts,
            execution_feedback=feedback,
            planner_signal=planner_signal,
        )

    def extract_artifacts(self, data: Any) -> List[Dict[str, Any]]:
        artifacts: List[Dict[str, Any]] = []
        if not isinstance(data, dict):
            return artifacts
        for key in ("path", "file", "file_path", "output_path"):
            value = data.get(key)
            if isinstance(value, str):
                artifacts.append({"type": "file_ref", "key": key, "path": value})
        files = data.get("files")
        if isinstance(files, list):
            for item in files:
                if isinstance(item, str):
                    artifacts.append({"type": "file_ref", "key": "files", "path": item})
        return artifacts

    def extract_execution_feedback(self, raw_result: Any, data: Any, success: bool) -> Dict[str, Any]:
        feedback = {
            "action_status": "success" if success else "failure",
            "recommended_action": "continue" if success else "retry",
            "confidence": None,
            "blocking_reason": None,
            "world_state": None,
            "error_type": None,
            "failure_category": None,
        }

        for attr in (
            "action_status",
            "recommended_action",
            "confidence",
            "blocking_reason",
            "world_state",
            "error_type",
            "failure_category",
        ):
            if hasattr(raw_result, attr):
                value = getattr(raw_result, attr)
                if value is not None:
                    feedback[attr] = value

        if isinstance(data, dict):
            if data.get("success") is False and feedback["action_status"] == "success":
                feedback["action_status"] = "failure"

            for key in (
                "action_status",
                "recommended_action",
                "confidence",
                "blocking_reason",
                "world_state",
                "error_type",
                "failure_category",
            ):
                if key in data and data.get(key) is not None:
                    feedback[key] = data.get(key)

            if feedback["world_state"] is None:
                world_state = {}
                for key in (
                    "observed_before",
                    "observed_after",
                    "readiness",
                    "validation",
                    "state",
                    "state_check",
                    "grounded",
                    "grounding",
                    "visual_state",
                    "active_window_title",
                    "target",
                    "requested_field",
                    "field_value",
                    "answer_ready",
                    "ambiguous",
                ):
                    if key in data:
                        world_state[key] = data.get(key)
                if world_state:
                    feedback["world_state"] = world_state

            readiness = data.get("readiness")
            if readiness in {"loading", "not_ready", "pending"} and feedback["recommended_action"] == "continue":
                feedback["recommended_action"] = "wait_and_retry"
                feedback["action_status"] = "partial"
                feedback["blocking_reason"] = feedback["blocking_reason"] or f"readiness:{readiness}"

        if feedback["action_status"] is None:
            feedback["action_status"] = "success" if success else "failure"
        if feedback["recommended_action"] is None:
            feedback["recommended_action"] = "continue" if success else "retry"

        return feedback

    def _build_planner_signal(
        self,
        tool_name: str,
        operation: str,
        data: Any,
        success: bool,
        error: Optional[str],
        artifacts: List[Dict[str, Any]],
        feedback: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Condense the result into a planner-facing summary."""
        return {
            "tool_name": tool_name,
            "operation": operation,
            "success": success,
            "error": error,
            "action_status": feedback.get("action_status"),
            "recommended_action": feedback.get("recommended_action"),
            "world_state": feedback.get("world_state"),
            "error_type": feedback.get("error_type"),
            "failure_category": feedback.get("failure_category"),
            "artifacts": artifacts,
            "output_summary": self._summarize_output(data),
        }

    def _summarize_output(self, data: Any, max_chars: int = 300) -> str:
        if data is None:
            return ""
        try:
            if isinstance(data, (dict, list)):
                text = json.dumps(data, default=str)
            else:
                text = str(data)
        except Exception:
            text = str(data)
        return text[:max_chars] + ("..." if len(text) > max_chars else "")
