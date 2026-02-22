"""Task Planner - Breaks down complex goals into executable steps."""
import json
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TaskStep:
    """Single step in execution plan."""
    step_id: str
    description: str
    tool_name: str
    operation: str
    parameters: Dict[str, Any]
    dependencies: List[str]  # step_ids that must complete first
    expected_output: str
    retry_on_failure: bool = True
    max_retries: int = 3


@dataclass
class ExecutionPlan:
    """Complete execution plan for a goal."""
    goal: str
    steps: List[TaskStep]
    estimated_duration: int  # seconds
    complexity: str  # simple, moderate, complex
    requires_approval: bool = False


class TaskPlanner:
    """Plans multi-step task execution from user goals."""
    
    def __init__(self, llm_client, tool_registry):
        self.llm_client = llm_client
        self.tool_registry = tool_registry
    
    def plan_task(self, user_goal: str, context: Optional[Dict] = None) -> ExecutionPlan:
        """
        Convert user goal into executable plan.
        
        Args:
            user_goal: Natural language goal
            context: Optional context (previous results, user preferences)
        
        Returns:
            ExecutionPlan with ordered steps
        """
        logger.info(f"Planning task for goal: {user_goal}")
        
        # Get available tools and their capabilities
        available_tools = self._get_tool_capabilities()
        
        # Build planning prompt
        prompt = self._build_planning_prompt(user_goal, available_tools, context)
        
        # Get plan from LLM
        try:
            response = self.llm_client._call_llm(
                prompt,
                temperature=0.3,
                max_tokens=2000
            )
            
            # Parse LLM response into structured plan
            plan_data = self._parse_plan_response(response)
            
            # Validate and optimize plan
            plan = self._validate_plan(plan_data, user_goal)
            
            logger.info(f"Generated plan with {len(plan.steps)} steps")
            return plan
            
        except Exception as e:
            logger.error(f"Planning failed: {e}")
            raise RuntimeError(f"Failed to create execution plan: {e}")
    
    def _get_tool_capabilities(self) -> Dict[str, List[Dict]]:
        """Get all available tools and their capabilities from live registry."""
        tools_info = {}
        
        # Get fresh tools list from registry (not cached)
        current_tools = getattr(self.tool_registry, 'tools', [])
        
        for tool_instance in current_tools:
            tool_name = tool_instance.__class__.__name__
            
            # Skip ShellTool for browser/web tasks to avoid confusion
            if tool_name == "ShellTool":
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
                tools_info[tool_name] = capabilities
        
        return tools_info
    
    def _build_planning_prompt(self, goal: str, tools: Dict, context: Optional[Dict]) -> str:
        """Build prompt for LLM to generate plan."""
        tools_desc = json.dumps(tools, indent=2)
        context_str = json.dumps(context, indent=2) if context else "None"
        
        return f"""You are a task planning AI. Break down the user's goal into executable steps using available tools.

USER GOAL: {goal}

AVAILABLE TOOLS:
{tools_desc}

CONTEXT:
{context_str}

CRITICAL TOOL SELECTION RULES:
- For browser tasks (open website, search, navigate, screenshot): Use BrowserAutomationTool
- For file operations (read, write, list): Use FilesystemTool  
- For HTTP requests (API calls): Use HTTPTool
- For shell commands (ls, pwd): Use ShellTool
- For text summarization: Use ContextSummarizerTool
- For database queries: Use DatabaseQueryTool

Generate a JSON execution plan with this structure:
{{
  "goal": "restated goal",
  "complexity": "simple|moderate|complex",
  "estimated_duration": <seconds>,
  "requires_approval": true/false,
  "steps": [
    {{
      "step_id": "step_1",
      "description": "what this step does",
      "tool_name": "ToolName",
      "operation": "operation_name",
      "parameters": {{}},
      "dependencies": [],
      "expected_output": "what we expect",
      "retry_on_failure": true
    }}
  ]
}}

CRITICAL RULES:
1. ALL required parameters MUST be provided with actual values from the user goal
2. For "open google": use BrowserAutomationTool with open_and_navigate operation and url="https://www.google.com"
3. For "search X": use BrowserAutomationTool with type_text operation
4. For "screenshot": use BrowserAutomationTool with take_screenshot operation
5. Steps must be ordered - dependencies execute first
6. Use only available tools and operations
7. Parameters must match tool requirements exactly

EXAMPLE - "open google and search autonomous agents":
{{
  "goal": "Open Google and search for autonomous agents",
  "complexity": "simple",
  "estimated_duration": 10,
  "requires_approval": false,
  "steps": [
    {{
      "step_id": "step_1",
      "description": "Open Google and search",
      "tool_name": "BrowserAutomationTool",
      "operation": "open_and_navigate",
      "parameters": {{"url": "https://www.google.com/search?q=autonomous+agents"}},
      "dependencies": [],
      "expected_output": "Browser opened to Google search results",
      "retry_on_failure": true
    }},
    {{
      "step_id": "step_2",
      "description": "Take screenshot of results",
      "tool_name": "BrowserAutomationTool",
      "operation": "take_screenshot",
      "parameters": {{}},
      "dependencies": ["step_1"],
      "expected_output": "Screenshot captured",
      "retry_on_failure": true
    }}
  ]
}}

Return ONLY valid JSON, no explanation."""
    
    def _parse_plan_response(self, response: str) -> Dict:
        """Parse LLM response into plan data."""
        # Extract JSON from response
        response = response.strip()
        
        # Try to find JSON block
        if "```json" in response:
            start = response.find("```json") + 7
            end = response.find("```", start)
            response = response[start:end].strip()
        elif "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            response = response[start:end].strip()
        
        try:
            return json.loads(response)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse plan JSON: {e}\nResponse: {response}")
            raise ValueError(f"Invalid plan format: {e}")
    
    def _validate_plan(self, plan_data: Dict, original_goal: str) -> ExecutionPlan:
        """Validate and convert plan data to ExecutionPlan."""
        # Validate required fields
        required = ["goal", "steps", "complexity", "estimated_duration"]
        for field in required:
            if field not in plan_data:
                raise ValueError(f"Missing required field: {field}")
        
        # Get fresh tools from registry
        current_tools = {tool.__class__.__name__: tool for tool in getattr(self.tool_registry, 'tools', [])}
        
        # Validate steps
        steps = []
        for step_data in plan_data["steps"]:
            # Check tool exists
            tool_name = step_data.get("tool_name")
            if tool_name not in current_tools:
                logger.warning(f"Unknown tool: {tool_name}, skipping step")
                continue
            
            tool = current_tools[tool_name]
            
            # Check operation exists
            operation = step_data.get("operation")
            capabilities = tool.get_capabilities() or {}
            if operation not in capabilities:
                logger.warning(f"Unknown operation {operation} for tool {tool_name}, skipping step")
                continue
            
            # Validate required parameters are provided
            capability = capabilities[operation]
            provided_params = step_data.get("parameters", {})
            missing_required = []
            
            for param in capability.parameters:
                if param.required and param.name not in provided_params:
                    missing_required.append(param.name)
            
            if missing_required:
                logger.warning(f"Step {step_data['step_id']} missing required params: {missing_required}, skipping")
                continue
            
            # Create TaskStep
            step = TaskStep(
                step_id=step_data["step_id"],
                description=step_data["description"],
                tool_name=tool_name,
                operation=operation,
                parameters=provided_params,
                dependencies=step_data.get("dependencies", []),
                expected_output=step_data.get("expected_output", ""),
                retry_on_failure=step_data.get("retry_on_failure", True),
                max_retries=step_data.get("max_retries", 3)
            )
            steps.append(step)
        
        if not steps:
            raise ValueError("No valid steps in plan - all steps were invalid or missing required parameters")
        
        # Validate dependency graph (no cycles)
        self._validate_dependencies(steps)
        
        return ExecutionPlan(
            goal=plan_data["goal"],
            steps=steps,
            estimated_duration=plan_data["estimated_duration"],
            complexity=plan_data["complexity"],
            requires_approval=plan_data.get("requires_approval", False)
        )
    
    def _validate_dependencies(self, steps: List[TaskStep]):
        """Ensure no circular dependencies."""
        step_ids = {step.step_id for step in steps}
        
        for step in steps:
            # Check all dependencies exist
            for dep_id in step.dependencies:
                if dep_id not in step_ids:
                    raise ValueError(f"Step {step.step_id} depends on unknown step {dep_id}")
            
            # Check for cycles (simple check - can be improved)
            visited = set()
            self._check_cycle(step.step_id, steps, visited)
    
    def _check_cycle(self, step_id: str, steps: List[TaskStep], visited: set):
        """Recursively check for dependency cycles."""
        if step_id in visited:
            raise ValueError(f"Circular dependency detected involving {step_id}")
        
        visited.add(step_id)
        
        step = next((s for s in steps if s.step_id == step_id), None)
        if step:
            for dep_id in step.dependencies:
                self._check_cycle(dep_id, steps, visited.copy())
