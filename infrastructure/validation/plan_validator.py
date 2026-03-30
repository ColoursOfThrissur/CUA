"""Plan Validator - Validates and normalizes execution plans."""
import json
import logging
from typing import Dict, List, Any, Optional
from domain.entities.task import TaskStep, ExecutionPlan

logger = logging.getLogger(__name__)


class PlanValidator:
    """Validates execution plans."""
    
    # Operation aliases
    _OP_ALIASES = {
        "fill_form": "fill_input", "fill_form_field": "fill_input", "type_text": "fill_input",
        "input_text": "fill_input", "enter_text": "fill_input", "open_url": "navigate",
        "open_browser": "navigate", "go_to": "navigate", "goto": "navigate",
        "press_key": "keyboard_action", "key_press": "keyboard_action",
        "screenshot": "take_screenshot", "get_current_page": "get_page_content",
        "get_page_source": "get_page_content", "read_page": "get_page_content",
        "morning_note": "generate_morning_note", "morning_brief": "generate_morning_note",
        "full_report": "generate_full_report", "advisor_insight": "get_advisor_insight",
    }
    
    def __init__(self, tool_registry):
        self.tool_registry = tool_registry
    
    def validate(self, plan_data: Dict, original_goal: str) -> ExecutionPlan:
        """Validate and convert plan data to ExecutionPlan."""
        required = ["goal", "steps", "complexity", "estimated_duration"]
        for field in required:
            if field not in plan_data:
                raise ValueError(f"Missing required field: {field}")
        
        current_tools = self._build_tool_index()
        steps = []
        skipped_ids = set()
        
        for step_data in plan_data["steps"]:
            step_id = step_data.get("step_id", "?")
            tool_name = step_data.get("tool_name")
            
            if tool_name not in current_tools:
                logger.warning(f"Unknown tool: {tool_name}, skipping step {step_id}")
                skipped_ids.add(step_id)
                continue
            
            tool = current_tools[tool_name]
            operation = step_data.get("operation")
            capabilities = tool.get_capabilities() or {}
            
            # Remap operation aliases
            if operation not in capabilities:
                remapped = self._OP_ALIASES.get(operation)
                if remapped and remapped in capabilities:
                    logger.warning(f"Remapping op '{operation}' → '{remapped}' for {tool_name}")
                    operation = remapped
                else:
                    logger.warning(f"Unknown operation '{operation}' for {tool_name}, skipping step {step_id}")
                    skipped_ids.add(step_id)
                    continue
            
            capability = capabilities[operation]
            provided_params = step_data.get("parameters", {})
            
            # Normalize parameters
            provided_params = self._normalize_params(provided_params, capability)
            
            # Check required params
            missing_required = [
                p.name for p in capability.parameters
                if p.required and p.name not in provided_params
            ]
            if missing_required:
                logger.warning(f"Step {step_id} missing required params: {missing_required}, skipping")
                skipped_ids.add(step_id)
                continue
            
            # Fix dependencies
            raw_deps = step_data.get("dependencies", [])
            if raw_deps and all(d in skipped_ids for d in raw_deps):
                logger.warning(f"Step {step_id} all dependencies skipped, cascading skip")
                skipped_ids.add(step_id)
                continue
            deps = [d for d in raw_deps if d not in skipped_ids]
            
            steps.append(TaskStep(
                step_id=step_id,
                description=step_data["description"],
                tool_name=tool_name,
                operation=operation,
                parameters=provided_params,
                domain=step_data.get("domain", "general"),
                dependencies=deps,
                expected_output=step_data.get("expected_output", ""),
                retry_on_failure=step_data.get("retry_on_failure", True),
                max_retries=step_data.get("max_retries", 3),
                preconditions=step_data.get("preconditions", []),
                postconditions=step_data.get("postconditions", []),
                checkpoint_policy=step_data.get("checkpoint_policy", "on_failure"),
                retry_policy=step_data.get("retry_policy", {}),
            ))
        
        if not steps:
            raise ValueError("No valid steps in plan")
        
        # Auto-fix browser navigation
        self._fix_browser_navigation(steps)
        
        # Auto-fix get_current_page dependencies
        self._fix_page_content_dependencies(steps, plan_data["steps"])
        
        # Validate dependencies
        self._validate_dependencies(steps)
        
        return ExecutionPlan(
            goal=plan_data["goal"],
            steps=steps,
            estimated_duration=plan_data["estimated_duration"],
            complexity=plan_data["complexity"],
            requires_approval=plan_data.get("requires_approval", False)
        )
    
    def _build_tool_index(self) -> Dict:
        """Build tool name → tool instance index."""
        current_tools = {}
        for tool in getattr(self.tool_registry, 'tools', []):
            current_tools[tool.__class__.__name__] = tool
            inst = getattr(tool, 'name', None)
            if inst and not callable(inst):
                current_tools[inst] = tool
        return current_tools
    
    def _normalize_params(self, params: Dict, capability) -> Dict:
        """Remap common param name variants."""
        real_names = {p.name for p in capability.parameters}
        aliases = {
            "element_selector": "selector", "css_selector": "selector",
            "xpath": "selector", "value": "text", "input_text": "text",
            "content": "text", "javascript": "script", "js": "script", "code": "script",
        }
        result = dict(params)
        for alias, real in aliases.items():
            if alias in result and alias not in real_names and real in real_names and real not in result:
                result[real] = result.pop(alias)
        return result
    
    def _fix_browser_navigation(self, steps: List[TaskStep]):
        """Serialize parallel navigate steps (shared browser)."""
        nav_steps = [
            s for s in steps
            if s.tool_name == "BrowserAutomationTool" and s.operation == "navigate" and not s.dependencies
        ]
        if len(nav_steps) > 1:
            for i in range(1, len(nav_steps)):
                nav_steps[i].dependencies = [nav_steps[i - 1].step_id]
                logger.info(f"Auto-serialized navigate {nav_steps[i].step_id} → {nav_steps[i-1].step_id}")
    
    def _fix_page_content_dependencies(self, steps: List[TaskStep], original_steps: List[Dict]):
        """Auto-pair get_current_page with closest navigate."""
        all_step_ids = [s.step_id for s in steps]
        nav_step_ids = {
            s.step_id for s in steps
            if s.tool_name == "BrowserAutomationTool" and s.operation == "navigate"
        }
        
        for s in steps:
            if s.operation == "get_current_page" and not s.dependencies:
                current_idx = all_step_ids.index(s.step_id)
                prior_navs = [
                    ps.step_id for ps in steps
                    if ps.operation == "navigate" and all_step_ids.index(ps.step_id) < current_idx
                ]
                if prior_navs:
                    s.dependencies = [prior_navs[-1]]
                    logger.info(f"Auto-paired {s.step_id} → {prior_navs[-1]}")
    
    def _validate_dependencies(self, steps: List[TaskStep]):
        """Ensure no circular dependencies."""
        step_ids = {step.step_id for step in steps}
        
        for step in steps:
            for dep_id in step.dependencies:
                if dep_id not in step_ids:
                    raise ValueError(f"Step {step.step_id} depends on unknown step {dep_id}")
            
            visited = set()
            self._check_cycle(step.step_id, steps, visited)
    
    def _check_cycle(self, step_id: str, steps: List[TaskStep], visited: set):
        """Recursively check for cycles."""
        if step_id in visited:
            raise ValueError(f"Circular dependency detected involving {step_id}")
        
        visited.add(step_id)
        step = next((s for s in steps if s.step_id == step_id), None)
        if step:
            for dep_id in step.dependencies:
                self._check_cycle(dep_id, steps, visited.copy())
    
    def parse_llm_response(self, response: str) -> Dict:
        """Parse LLM JSON response."""
        response = response.strip()
        
        if "```json" in response:
            start = response.find("```json") + 7
            end = response.find("```", start)
            response = response[start:end].strip()
        elif "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            response = response[start:end].strip()
        
        try:
            import re
            cleaned = self._strip_comments(response)
            cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)
            cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', cleaned)
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse plan JSON: {e}")
            raise ValueError(f"Invalid plan format: {e}")
    
    def _strip_comments(self, s: str) -> str:
        """Strip // comments outside strings."""
        result = []
        in_string = False
        escape_next = False
        i = 0
        while i < len(s):
            ch = s[i]
            if escape_next:
                result.append(ch)
                escape_next = False
            elif ch == '\\':
                result.append(ch)
                escape_next = True
            elif ch == '"':
                result.append(ch)
                in_string = not in_string
            elif not in_string and ch == '/' and i + 1 < len(s) and s[i+1] == '/':
                while i < len(s) and s[i] != '\n':
                    i += 1
                continue
            else:
                result.append(ch)
            i += 1
        return ''.join(result)
