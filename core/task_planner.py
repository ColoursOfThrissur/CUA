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
    domain: str = "general"
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
    
    def __init__(self, llm_client, tool_registry, skill_registry=None):
        self.llm_client = llm_client
        self.tool_registry = tool_registry
        self.skill_registry = skill_registry
    
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
        
        # Force registry refresh to get latest tools
        if hasattr(self.tool_registry, 'refresh'):
            try:
                self.tool_registry.refresh()
                logger.info("Registry refreshed before planning")
            except Exception as e:
                logger.warning(f"Failed to refresh registry: {e}")
        
        # Get fresh tools list from registry (not cached)
        current_tools = getattr(self.tool_registry, 'tools', [])
        raw_web_tools_hidden = any(
            tool.__class__.__name__ == "WebAccessTool" for tool in current_tools
        )
        
        for tool_instance in current_tools:
            tool_name = tool_instance.__class__.__name__
            if raw_web_tools_hidden and tool_name in {"HTTPTool", "BrowserAutomationTool"}:
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
        skill_guidance = self._build_skill_guidance(context)
        domain_guidance = self._build_domain_guidance(context)
        
        return f"""You are a task planning AI. Break down the user's goal into executable steps using available tools.

USER GOAL: {goal}

AVAILABLE TOOLS:
{tools_desc}

CONTEXT:
{context_str}

SKILL GUIDANCE:
{skill_guidance}

DOMAIN CATALOG:
{domain_guidance}

CRITICAL TOOL SELECTION RULES:
- For web retrieval, searches, page opening, page extraction, or light crawling: Use WebAccessTool
- For file operations (read, write, list): Use FilesystemTool  
- For shell commands (ls, pwd): Use ShellTool
- For text summarization: Use ContextSummarizerTool
- For database queries: Use DatabaseQueryTool
- Prefer WebAccessTool.fetch_url for web content retrieval, WebAccessTool.search_web for searches, WebAccessTool.open_page for interactive page opening, WebAccessTool.get_current_page after prior browser navigation, and WebAccessTool.crawl_site for small same-site crawls.

Generate a JSON execution plan with this structure:
{{
  "goal": "restated goal",
  "complexity": "simple|moderate|complex",
  "estimated_duration": <seconds>,
  "requires_approval": true/false,
  "steps": [
    {{
      "step_id": "step_1",
      "domain": "web|computer|development|other",
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
1b. Choose the best domain for EACH step. A plan may use multiple domains across different steps.
2. For "open google": use WebAccessTool with open_page and url="https://www.google.com"
3. For "search X": prefer WebAccessTool.search_web with query="X" and do not force google unless the user explicitly asks for it
4. For "fetch or summarize a page": prefer WebAccessTool.fetch_url with the page URL
4b. For "crawl this site" or "collect multiple pages": prefer WebAccessTool.crawl_site with start_url and max_pages
4c. For "after opening/searching, read what is on the page": use WebAccessTool.get_current_page
5. Steps must be ordered - dependencies execute first
6. Use only available tools and operations
7. Parameters must match tool requirements exactly
8. Never invent unsupported operations or bypass the higher-level web tool when WebAccessTool is available

EXAMPLE - "open google and search autonomous agents":
{{
  "goal": "Open Google and search for autonomous agents",
  "complexity": "simple",
  "estimated_duration": 10,
  "requires_approval": false,
  "steps": [
    {{
      "step_id": "step_1",
      "domain": "web",
      "description": "Open Google and search",
      "tool_name": "WebAccessTool",
      "operation": "search_web",
      "parameters": {{"query": "autonomous agents"}},
      "dependencies": [],
      "expected_output": "Search results content returned",
      "retry_on_failure": true
    }}
  ]
}}

Return ONLY valid JSON, no explanation."""

    def _build_skill_guidance(self, context: Optional[Dict]) -> str:
        skill_context = (context or {}).get("skill_context")
        if not skill_context:
            return "No skill selected. Plan from the available tools and user goal only."

        return (
            f"Selected skill: {skill_context.get('skill_name', 'unknown')}\n"
            f"Category: {skill_context.get('category', 'unknown')}\n"
            f"Instructions summary: {skill_context.get('instructions_summary', '')}\n"
            f"Preferred tools: {', '.join(skill_context.get('preferred_tools', [])) or 'none'}\n"
            f"Required tools: {', '.join(skill_context.get('required_tools', [])) or 'none'}\n"
            f"Verification mode: {skill_context.get('verification_mode', 'default')}\n"
            f"Expected outputs: {', '.join(skill_context.get('output_types', [])) or 'unspecified'}\n"
            f"Constraints: {'; '.join(skill_context.get('skill_constraints', [])) or 'none'}"
        )

    def _build_domain_guidance(self, context: Optional[Dict]) -> str:
        domain_catalog = (context or {}).get("domain_catalog")
        if not domain_catalog:
            return "No domain catalog available."

        return json.dumps(domain_catalog, indent=2)
    
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
        
        # Force registry refresh to get latest tools
        if hasattr(self.tool_registry, 'refresh'):
            try:
                self.tool_registry.refresh()
            except Exception as e:
                logger.warning(f"Failed to refresh registry during validation: {e}")
        
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
                domain=step_data.get("domain") or self._infer_domain_for_tool(tool_name, context=plan_data),
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

    def _infer_domain_for_tool(self, tool_name: str, context: Optional[Dict] = None) -> str:
        domain_catalog = (context or {}).get("domain_catalog") if isinstance(context, dict) else None
        if domain_catalog:
            for domain in domain_catalog.get("domains", []):
                if any(tool.get("name") == tool_name for tool in domain.get("tools", [])):
                    return domain.get("name", "general")
        return "general"
    
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
