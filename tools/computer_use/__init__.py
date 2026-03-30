"""
Computer Use Tools - Agent-optimized desktop automation.

Four-agent architecture with Observe→Act→Evaluate→Adapt loop:
- ComputerUseController: Orchestrates feedback loop
- PlannerAgent: Intent → Plan
- ExecutorAgent: Plan → Execution Trace
- VerifierAgent: Trace → Success/Failure Analysis  
- CriticAgent: Failure → Adaptation Strategy

Three execution tools:
- ScreenPerceptionTool: Vision, caching, structured UI detection
- InputAutomationTool: Mouse/keyboard with retry loops
- SystemControlTool: Window/process management with safety
"""
from .computer_use_controller import ComputerUseController
from .planner_agent import PlannerAgent
from .executor_agent import ExecutorAgent
from .verifier_agent import VerifierAgent
from .critic_agent import CriticAgent
from .screen_perception_tool import ScreenPerceptionTool
from .input_automation_tool import InputAutomationTool
from .system_control_tool import SystemControlTool

__all__ = [
    "ComputerUseController",
    "PlannerAgent",
    "ExecutorAgent",
    "VerifierAgent",
    "CriticAgent",
    "ScreenPerceptionTool",
    "InputAutomationTool",
    "SystemControlTool",
]
