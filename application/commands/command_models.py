from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from domain.policies.immutable_brain_stem import RiskLevel


@dataclass
class CommandContext:
    runtime: Any
    session_id: str
    request_message: str
    sessions: Dict[str, Any]


@dataclass
class CommandResult:
    response_text: str
    success: bool = True
    execution_result: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CommandDefinition:
    name: str
    description: str
    handler: Callable[[CommandContext, str], CommandResult]
    aliases: List[str] = field(default_factory=list)
    category: str = "system"
    allowed_tools: List[str] = field(default_factory=list)
    requires_confirmation: bool = False
    risk_level: RiskLevel = RiskLevel.SAFE
