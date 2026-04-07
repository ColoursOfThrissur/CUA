"""Persistent task artifact models for workflow tracking."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TaskArtifactStep:
    """Persistent summary of one execution step in a tracked task."""

    subtask_id: str
    title: str
    methods: List[str]
    status: str = "pending"
    attempts: int = 0
    max_attempts: int = 1
    error: Optional[str] = None
    output_preview: Optional[str] = None


@dataclass
class TaskArtifact:
    """Persistent user-facing workflow object for a plan and its execution state."""

    task_id: str
    session_id: str
    description: str
    goal: str
    status: str
    priority: str
    source: str
    total_subtasks: int
    completed_subtasks: int = 0
    target_file: str = ""
    execution_id: Optional[str] = None
    plan: Optional[Dict[str, Any]] = None
    subtasks: List[TaskArtifactStep] = field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    completed_at: Optional[str] = None

