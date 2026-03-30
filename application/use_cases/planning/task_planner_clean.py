"""Task Planner Adapter - Bridges old interface to new clean architecture.

This adapter maintains backward compatibility while delegating to the new use cases.
"""
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

# Import old interfaces for compatibility
from domain.entities.task import TaskStep, ExecutionPlan
from application.planning.create_plan import CreatePlanUseCase
from application.planning.replan_steps import ReplanStepsUseCase
from infrastructure.llm.llm_gateway import OllamaLLMGateway
from infrastructure.llm.prompt_builder import PlanningPromptBuilder
from infrastructure.validation.plan_validator import PlanValidator

logger = logging.getLogger(__name__)


# Repository implementations
class ToolRegistryAdapter:
    """Adapts tool registry to repository interface."""
    
    def __init__(self, tool_registry):
        self.registry = tool_registry
    
    def get_capabilities(self, preferred_tools: Optional[set] = None) -> Dict[str, List[Dict]]:
        """Get tool capabilities."""
        _CORE = {"FilesystemTool", "WebAccessTool", "ShellTool", "JSONTool", "ContextSummarizerTool"}
        tools_info = {}
        
        if hasattr(self.registry, 'refresh'):
            try:
                self.registry.refresh()
            except Exception:
                pass
        
        current_tools = getattr(self.registry, 'tools', [])
        allowed = (set(preferred_tools) | _CORE) if preferred_tools else None
        
        for tool_instance in current_tools:
            tool_name = tool_instance.__class__.__name__
            instance_name = getattr(tool_instance, 'name', tool_name)
            if callable(instance_name):
                instance_name = tool_name
            
            is_mcp = tool_name.startswith("MCPAdapterTool")
            if allowed and instance_name not in allowed and tool_name not in allowed and not is_mcp:
                continue
            
            capabilities = []
            tool_caps = tool_instance.get_capabilities() or {}
            for cap_name, capability in tool_caps.items():
                capabilities.append({
                    "name": cap_name,
                    "description": capability.description,
                    "parameters": [
                        {
                            "name": p.name,
                            "type": p.type.value,
                            "description": p.description,
                            "required": p.required
                        }
                        for p in capability.parameters
                    ]
                })
            
            if capabilities:
                tools_info[instance_name] = capabilities
        
        return tools_info
    
    def get_tool(self, tool_name: str) -> Any:
        """Get tool by name."""
        for tool in getattr(self.registry, 'tools', []):
            if tool.__class__.__name__ == tool_name:
                return tool
            inst = getattr(tool, 'name', None)
            if inst and not callable(inst) and inst == tool_name:
                return tool
        return None
    
    def tool_exists(self, tool_name: str) -> bool:
        """Check if tool exists."""
        return self.get_tool(tool_name) is not None


class MemoryRepositoryAdapter:
    """Adapts memory systems to repository interface."""
    
    def __init__(self, strategic_memory):
        self.strategic_memory = strategic_memory
    
    def find_similar_plans(self, goal: str, skill_name: str, top_k: int = 3) -> List[Any]:
        """Find similar past plans."""
        return self.strategic_memory.retrieve(goal, skill_name=skill_name, top_k=top_k)
    
    def search_context(self, query: str, skill_name: str) -> str:
        """Search unified memory."""
        try:
            from infrastructure.persistence.file_storage.unified_memory import get_unified_memory
            return get_unified_memory().search_for_planning(query, skill_name)
        except Exception:
            return ""


class TaskPlanner:
    """Adapter that maintains old TaskPlanner interface using new clean architecture."""
    
    def __init__(self, llm_client, tool_registry, skill_registry=None):
        self.llm_client = llm_client
        self.tool_registry = tool_registry
        self.skill_registry = skill_registry
        
        # Initialize strategic memory (old way for compatibility)
        from infrastructure.persistence.file_storage.strategic_memory import get_strategic_memory
        self.strategic_memory = get_strategic_memory()
        
        # Create adapters
        tool_repo = ToolRegistryAdapter(tool_registry)
        memory_repo = MemoryRepositoryAdapter(self.strategic_memory)
        
        # Create infrastructure components
        llm_gateway = OllamaLLMGateway(llm_client)
        prompt_builder = PlanningPromptBuilder()
        plan_validator = PlanValidator(tool_registry)
        
        # Create use cases
        self._create_plan_uc = CreatePlanUseCase(
            llm_gateway=llm_gateway,
            tool_repo=tool_repo,
            memory_repo=memory_repo,
            prompt_builder=prompt_builder,
            plan_validator=plan_validator
        )
        
        self._replan_steps_uc = ReplanStepsUseCase(
            llm_gateway=llm_gateway,
            tool_repo=tool_repo,
            prompt_builder=prompt_builder,
            plan_validator=plan_validator
        )
    
    def plan_task(self, user_goal: str, context: Optional[Dict] = None) -> ExecutionPlan:
        """Create execution plan (delegates to use case)."""
        return self._create_plan_uc.execute(user_goal, context)
    
    def replan_remaining(
        self,
        original_goal: str,
        remaining_steps: List[TaskStep],
        replan_context: Dict,
        context: Optional[Dict] = None,
    ) -> List[TaskStep]:
        """Replan remaining steps (delegates to use case)."""
        return self._replan_steps_uc.execute(original_goal, remaining_steps, replan_context, context)
    
    def is_task_complete(
        self,
        goal: str,
        completed_steps: List[Dict],
        execution_result: Dict,
        verification_result: Dict
    ) -> Dict:
        """Evaluate if task is complete (kept for compatibility)."""
        # This could be moved to a separate use case, but keeping inline for now
        import json
        
        steps_summary = []
        for step in completed_steps:
            tool = step.get("tool", "")
            operation = step.get("operation", "")
            params = step.get("parameters", {})
            steps_summary.append(f"- {tool}.{operation}({', '.join(f'{k}={v}' for k, v in list(params.items())[:2])})")
        
        trace = execution_result.get("trace", [])
        for step in trace:
            tool = step.get("tool", "")
            operation = step.get("operation", "")
            result = step.get("result", {})
            success = result.get("success", False) if isinstance(result, dict) else False
            steps_summary.append(f"- {tool}.{operation}: {'✓' if success else '✗'}")
        
        prompt = f"""Evaluate if this task is fully complete.

ORIGINAL GOAL: {goal}

COMPLETED STEPS:
{chr(10).join(steps_summary) if steps_summary else '(none)'}

VERIFICATION: {verification_result.get('summary', 'Steps executed successfully')}

Is the ORIGINAL GOAL fully achieved? Consider:
- Multi-step tasks ("open X and do Y") need ALL parts done
- Inspection tasks ("list", "show", "find") need visual analysis completed
- File operations need both read/write completed

/no_think

Return ONLY JSON:
{{"complete": true/false, "reason": "brief explanation", "confidence": 0.0-1.0}}"""
        
        try:
            from shared.config.model_manager import get_model_manager
            model_manager = get_model_manager(self.llm_client)
            model_manager.switch_to("planning")
            
            response = self.llm_client._call_llm(
                prompt=prompt,
                temperature=0.1,
                max_tokens=150,
                expect_json=True
            )
            
            model_manager.switch_to("chat")
            
            if response:
                response = response.strip()
                if "```json" in response:
                    response = response[response.find("```json") + 7:response.rfind("```")].strip()
                elif "```" in response:
                    response = response[response.find("```") + 3:response.rfind("```")].strip()
                
                result = json.loads(response)
                is_complete = result.get("complete", False)
                reason = result.get("reason", "")
                confidence = result.get("confidence", 0.5)
                
                logger.info(f"Task completion check: {is_complete} (conf={confidence:.2f}) - {reason}")
                return {"complete": is_complete, "reason": reason, "confidence": confidence}
                
        except json.JSONDecodeError as e:
            logger.warning(f"Task check JSON format invalid: {e} - Response: {response}")
            # Ensure model switches back inside outer except block anyway
            pass
        except Exception as e:
            logger.warning(f"LLM completion check failed: {e}")
            
        try:
            from shared.config.model_manager import get_model_manager
            get_model_manager(self.llm_client).switch_to("chat")
        except Exception:
            pass
        
        fallback_complete = len(completed_steps) >= 2 and verification_result.get("verified")
        return {
            "complete": fallback_complete,
            "reason": "Fallback: multiple steps completed and verified",
            "confidence": 0.6 if fallback_complete else 0.3
        }
