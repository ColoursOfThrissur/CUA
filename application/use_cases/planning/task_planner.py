"""Task Planner - Clean Architecture Implementation.

This module now uses clean architecture with separated concerns:
- Domain entities in domain/entities/task.py
- Use cases in application/planning/
- Infrastructure in infrastructure/llm/ and infrastructure/validation/

The TaskPlanner class is now an adapter that maintains backward compatibility
while delegating to the new architecture.

See docs/ARCHITECTURE.md for the current planning/runtime architecture notes.
"""

# Re-export entities for backward compatibility
from domain.entities.task import TaskStep, ExecutionPlan

# Import the clean architecture adapter
from application.use_cases.planning.task_planner_clean import TaskPlanner

# Expose the same interface as before
__all__ = ['TaskPlanner', 'TaskStep', 'ExecutionPlan']

# Legacy class definition removed - now using clean architecture adapter
# Old monolithic implementation (1000+ lines) refactored into:
#   - domain/entities/task.py (40 lines)
#   - application/planning/create_plan.py (70 lines)
#   - application/planning/replan_steps.py (120 lines)
#   - infrastructure/llm/llm_gateway.py (60 lines)
#   - infrastructure/llm/prompt_builder.py (180 lines)
#   - infrastructure/validation/plan_validator.py (220 lines)
#   - application/use_cases/planning/task_planner_clean.py (200 lines adapter)

# The TaskPlanner class imported above maintains 100% backward compatibility
