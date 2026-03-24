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
        from core.strategic_memory import get_strategic_memory
        self.strategic_memory = get_strategic_memory()
    
    def replan_remaining(
        self,
        original_goal: str,
        remaining_steps: List["TaskStep"],
        replan_context: Dict,
        context: Optional[Dict] = None,
    ) -> List["TaskStep"]:
        """
        Regenerate only the remaining steps of a plan given what has already
        completed and what failed. Returns a new list of TaskStep objects
        that replace the original remaining steps.
        """
        logger.info(f"[PLANNER] Replanning {len(remaining_steps)} remaining steps for: '{original_goal[:60]}'")

        skill_preferred = set((context or {}).get("skill_context", {}).get("preferred_tools", []))
        available_tools = self._get_tool_capabilities(preferred_tools=skill_preferred or None)
        completed_summary = replan_context.get("completed_summary", {})
        failed_steps = replan_context.get("failed_steps", [])
        failed_errors = replan_context.get("failed_errors", {})

        completed_str = json.dumps(completed_summary, indent=2) if completed_summary else "None"
        failed_str = json.dumps(failed_errors, indent=2) if failed_errors else "None"
        remaining_desc = json.dumps(
            [{"step_id": s.step_id, "description": s.description, "tool": s.tool_name, "op": s.operation}
             for s in remaining_steps],
            indent=2
        )

        prompt = f"""You are replanning the remaining steps of a task that partially failed.

ORIGINAL GOAL: {original_goal}

COMPLETED STEPS (outputs available):
{completed_str}

FAILED STEPS (errors):
{failed_str}

ORIGINAL REMAINING STEPS (may need to change):
{remaining_desc}

AVAILABLE TOOLS:
{json.dumps(available_tools, indent=2)}

Generate replacement steps to achieve the original goal given what succeeded.
Use different tools/operations than the ones that failed.
Keep step_ids sequential from the last completed step.

PARALLELISM RULES:
- Steps with "dependencies": [] run IN PARALLEL with other dependency-free steps
- Only add a dependency when a step genuinely needs the OUTPUT of a prior step
- Always ask: "can this step start immediately?" — if yes, leave dependencies empty
- CRITICAL: get_current_page reads the CURRENTLY OPEN browser page — it MUST depend on the navigate/open_page step that loaded the page. Never put get_current_page in dependencies: []

Return ONLY a JSON array of steps:
[
  {{
    "step_id": "step_N",
    "description": "...",
    "tool_name": "ToolName",
    "operation": "operation_name",
    "parameters": {{}},
    "dependencies": [],
    "expected_output": "...",
    "domain": "web|computer|development|other",
    "retry_on_failure": true
  }}
]

Return ONLY valid JSON array, no explanation."""

        try:
            response = self.llm_client._call_llm(prompt, temperature=0.3, max_tokens=None, expect_json=True)
            if not response:
                raise RuntimeError("LLM returned no response during replan")
            response = response.strip()
            if "```json" in response:
                response = response[response.find("```json") + 7:response.rfind("```")].strip()
            elif "```" in response:
                response = response[response.find("```") + 3:response.rfind("```")].strip()

            steps_data = self._parse_plan_response(f'{{"steps": {response} }}')
            if isinstance(steps_data, dict):
                steps_data = steps_data.get("steps", steps_data)
            if not isinstance(steps_data, list):
                raise ValueError("Expected JSON array")

            current_tools = {t.__class__.__name__: t for t in getattr(self.tool_registry, "tools", [])}
            new_steps = []
            for sd in steps_data:
                tool_name = sd.get("tool_name")
                operation = sd.get("operation")
                if tool_name not in current_tools:
                    logger.warning(f"Replan: unknown tool {tool_name}, skipping")
                    continue
                tool = current_tools[tool_name]
                caps = tool.get_capabilities() or {}
                # Remap hallucinated op names
                if operation not in caps:
                    remapped = self._OP_ALIASES.get(operation)
                    if remapped and remapped in caps:
                        operation = remapped
                    else:
                        logger.warning(f"Replan: unknown op {operation} on {tool_name}, skipping")
                        continue
                capability = caps[operation]
                params = sd.get("parameters", {})
                params = self._normalize_params(params, capability)
                new_steps.append(TaskStep(
                    step_id=sd["step_id"],
                    description=sd["description"],
                    tool_name=tool_name,
                    operation=operation,
                    parameters=params,
                    dependencies=sd.get("dependencies", []),
                    expected_output=sd.get("expected_output", ""),
                    domain=sd.get("domain", "general"),
                    retry_on_failure=sd.get("retry_on_failure", True),
                    max_retries=sd.get("max_retries", 3),
                ))

            if new_steps:
                logger.info(f"[PLANNER] Replan produced {len(new_steps)} replacement steps")
                try:
                    self._validate_dependencies(new_steps)
                except ValueError as e:
                    logger.warning(f"Replan dependency validation failed: {e}, returning original steps")
                    return remaining_steps
                return new_steps

        except Exception as e:
            logger.error(f"Replan failed: {e}")

        # Fallback: return original remaining steps unchanged
        return remaining_steps

    def plan_task(self, user_goal: str, context: Optional[Dict] = None) -> ExecutionPlan:
        """
        Convert user goal into executable plan.
        
        Args:
            user_goal: Natural language goal
            context: Optional context (previous results, user preferences)
        
        Returns:
            ExecutionPlan with ordered steps
        """
        logger.info(f"[PLANNER] Planning task: '{user_goal[:80]}'")
        
        # Get available tools and their capabilities
        skill_preferred = set((context or {}).get("skill_context", {}).get("preferred_tools", []))
        available_tools = self._get_tool_capabilities(preferred_tools=skill_preferred or None)

        # Retrieve similar past plans to bias the LLM
        skill_name = (context or {}).get("skill_context", {}).get("skill_name", "")
        past_plans = self.strategic_memory.retrieve(user_goal, skill_name=skill_name, top_k=3)

        # Unified memory search — enriches prompt with cross-store context
        try:
            from core.unified_memory import get_unified_memory
            unified_context = get_unified_memory().search_for_planning(user_goal, skill_name)
        except Exception:
            unified_context = ""

        # Build planning prompt
        prompt = self._build_planning_prompt(user_goal, available_tools, context, past_plans, unified_context)
        
        # Get plan from LLM
        try:
            response = self.llm_client._call_llm(
                prompt,
                temperature=0.3,
                max_tokens=None,  # let ModelProfile decide (tokens_json per model family)
                expect_json=True
            )

            if not response:
                raise RuntimeError("LLM returned no response — check provider config (api_key, model, connectivity)")

            logger.info(f"[PLANNER] Raw response len={len(response)}, preview={response[:100]!r}")
            # Parse LLM response into structured plan
            plan_data = self._parse_plan_response(response)
            
            # Validate and optimize plan
            plan = self._validate_plan(plan_data, user_goal)
            
            logger.info(f"[PLANNER] Plan ready: {len(plan.steps)} steps, complexity={plan_data.get('complexity','?')}")
            return plan
            
        except Exception as e:
            logger.error(f"Planning failed: {e}")
            raise RuntimeError(f"Failed to create execution plan: {e}")
    
    def _get_tool_capabilities(self, preferred_tools: Optional[set] = None) -> Dict[str, List[Dict]]:
        """Get available tools and their capabilities from live registry.
        
        If preferred_tools is provided, only those tools (plus core tools) are returned.
        """
        _CORE = {"FilesystemTool", "WebAccessTool", "ShellTool", "JSONTool", "ContextSummarizerTool"}
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

        allowed = (set(preferred_tools) | _CORE) if preferred_tools else None
        
        for tool_instance in current_tools:
            tool_name = tool_instance.__class__.__name__
            if raw_web_tools_hidden and tool_name == "HTTPTool":
                continue
            if allowed and tool_name not in allowed:
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
    
    def _build_planning_prompt(self, goal: str, tools: Dict, context: Optional[Dict], past_plans: list = None, unified_context: str = "") -> str:
        """Build prompt for LLM to generate plan."""
        skill_name = (context or {}).get("skill_context", {}).get("skill_name", "")
        preferred = set((context or {}).get("skill_context", {}).get("preferred_tools", []))
        # Always include summarizer as optional utility
        preferred.add("ContextSummarizerTool")

        # Filter tool schema to preferred tools only; fall back to full set if no match
        filtered = {k: v for k, v in tools.items() if k in preferred} if preferred else tools
        if not filtered:
            filtered = tools

        compact_tools = {}
        for tool_name, caps in filtered.items():
            compact_tools[tool_name] = [
                {
                    "name": cap["name"],
                    "required": [p["name"] for p in cap.get("parameters", []) if p.get("required")],
                    "optional": [p["name"] for p in cap.get("parameters", []) if not p.get("required")],
                }
                for cap in caps
            ]
        tools_desc = json.dumps(compact_tools, indent=2)
        context_str = f"skill: {skill_name}" if skill_name else "None"
        skill_guidance = self._build_skill_guidance(context)
        domain_guidance = self._build_domain_guidance(context)
        past_plans_str = self._build_past_plans_guidance(past_plans or [])
        unified_str = unified_context.strip() if unified_context else "No additional memory context."
        examples = self._build_skill_examples(skill_name)

        return f"""You are a task planning AI. Break down the user's goal into executable steps using available tools.

USER GOAL: {goal}

MEMORY CONTEXT (past approaches for similar goals):
{unified_str}

PAST SUCCESSFUL APPROACHES:
{past_plans_str}

AVAILABLE TOOLS:
{tools_desc}

CONTEXT: {context_str}

SKILL GUIDANCE:
{skill_guidance}

EXAMPLES FOR THIS SKILL:
{examples}

PARALLELISM RULES:
- dependencies:[] means runs in parallel with other dependency-free steps
- Only add a dependency when a step needs the OUTPUT of a prior step
- Never run multiple BrowserAutomationTool.navigate in parallel (shared browser)
- get_current_page MUST depend on the navigate/fetch step that loaded the page
- take_screenshot MUST depend on the last navigate before it

Generate a JSON execution plan:
{{
  "goal": "restated goal",
  "complexity": "simple|moderate|complex",
  "estimated_duration": <seconds>,
  "requires_approval": false,
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

Return ONLY valid JSON, no explanation."""

    def _build_past_plans_guidance(self, past_plans: list) -> str:
        if not past_plans:
            return "No similar past plans found."
        lines = []
        for rec in past_plans:
            lines.append(
                f"- Goal: '{rec.goal_sample}' | Skill: {rec.skill_name} "
                f"| Win rate: {rec.win_rate():.0%} ({rec.success_count}✓/{rec.fail_count}✗) "
                f"| Avg duration: {rec.avg_duration_s:.1f}s"
            )
            for s in rec.steps[:6]:  # cap at 6 steps to keep prompt tight
                lines.append(f"    {s.get('tool','?')}.{s.get('operation','?')} [{s.get('domain','')}]")
        return "\n".join(lines)

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

    def _build_skill_examples(self, skill_name: str) -> str:
        examples = {
            "web_research": [
                '(web_research tasks are handled by the reactive WebResearchAgent — no DAG plan needed)',
            ],
            "browser_automation": [
                'Goal: "go to google and search cats" → navigate(url="https://google.com") → fill_input(selector="input[name=q]", text="cats", deps:[step_1]) → click_element(selector="input[type=submit]", deps:[step_2])',
                'Goal: "take screenshot of github" → navigate(url="https://github.com") → take_screenshot(deps:[step_1])',
                'NOTE: never run two navigate steps in parallel — shared browser instance.',
            ],
            "computer_automation": [
                'Goal: "list files in data folder" → list_directory(path="data")',
                'Goal: "read config.yaml and show contents" → read_file(path="config.yaml")',
            ],
            "code_workspace": [
                'Goal: "run tests" → execute(command="pytest -q")',
                'Goal: "read main.py" → read_file(path="main.py")',
            ],
            "data_operations": [
                'Goal: "parse this JSON string" → parse(text="{...}")',
                'Goal: "query tool execution logs" → query_logs(limit=20)',
            ],
            "knowledge_management": [
                'Goal: "save this code snippet" → save_snippet(name="...", code="...", language="python")',
                'Goal: "find snippets about auth" → search(query="auth")',
            ],
        }
        lines = examples.get(skill_name, [
            'Use the most appropriate tool for the goal.',
            'Prefer search_web for live/dynamic content, fetch_url for static pages.',
        ])
        return "\n".join(f"- {l}" for l in lines)

    def _build_domain_guidance(self, context: Optional[Dict]) -> str:
        domain_catalog = (context or {}).get("domain_catalog")
        if not domain_catalog:
            return "No domain catalog available."
        # Compact: just domain name → tool names, skip full descriptions
        lines = []
        for domain in (domain_catalog.get("domains") or []):
            tools = [t.get("name", "") for t in (domain.get("tools") or [])]
            lines.append(f"{domain.get('name', '?')}: {', '.join(tools)}")
        return "\n".join(lines) if lines else json.dumps(domain_catalog, indent=2)
    
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
            import re
            # Strip // comments only outside string values
            def _strip_comments(s):
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
                        # skip to end of line
                        while i < len(s) and s[i] != '\n':
                            i += 1
                        continue
                    elif in_string and ch == '\n':
                        result.append(' ')  # bare newline inside string → space
                    else:
                        result.append(ch)
                    i += 1
                return ''.join(result)
            cleaned = _strip_comments(response)
            cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)  # strip trailing commas
            cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', cleaned)  # strip control chars
            cleaned = re.sub(r'[\xa0\u00a0\u200b\u200c\u200d\u2028\u2029\ufeff\u00ad]', ' ', cleaned)  # normalize unicode spaces
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError as first_err:
                pos = first_err.pos
                snippet = cleaned[max(0, pos-20):pos+20]
                logger.error(f"JSON parse fail at pos {pos}, bytes: {[hex(ord(c)) for c in snippet]}")
                return json.loads(cleaned, strict=False)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse plan JSON: {e}\nResponse: {response}")
            raise ValueError(f"Invalid plan format: {e}")
    
    # Operation alias map: LLM hallucinations → real operation names
    _OP_ALIASES = {
        "fill_form": "fill_input",
        "fill_form_field": "fill_input",
        "fill_and_submit_form": "submit_form",
        "type_text": "fill_input",
        "input_text": "fill_input",
        "enter_text": "fill_input",
        "open_url": "navigate",
        "open_browser": "navigate",
        "go_to": "navigate",
        "goto": "navigate",
        "open_and_navigate": "navigate",
        "press_key": "keyboard_action",
        "key_press": "keyboard_action",
        "screenshot": "take_screenshot",
    }

    def _validate_plan(self, plan_data: Dict, original_goal: str) -> ExecutionPlan:
        """Validate and convert plan data to ExecutionPlan."""
        required = ["goal", "steps", "complexity", "estimated_duration"]
        for field in required:
            if field not in plan_data:
                raise ValueError(f"Missing required field: {field}")
        
        current_tools = {tool.__class__.__name__: tool for tool in getattr(self.tool_registry, 'tools', [])}
        
        steps = []
        skipped_ids = set()  # track skipped step_ids to fix dependencies

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

            # Remap hallucinated operation names to real ones
            if operation not in capabilities:
                remapped = self._OP_ALIASES.get(operation)
                if remapped and remapped in capabilities:
                    logger.warning(f"Remapping op '{operation}' → '{remapped}' for {tool_name} on step {step_id}")
                    operation = remapped
                else:
                    logger.warning(f"Unknown operation '{operation}' for {tool_name}, skipping step {step_id}")
                    skipped_ids.add(step_id)
                    continue
            
            capability = capabilities[operation]
            provided_params = step_data.get("parameters", {})

            # Auto-fix param name aliases (e.g. element_selector → selector)
            provided_params = self._normalize_params(provided_params, capability)

            missing_required = [
                p.name for p in capability.parameters
                if p.required and p.name not in provided_params
            ]
            if missing_required:
                logger.warning(f"Step {step_id} missing required params: {missing_required}, skipping")
                skipped_ids.add(step_id)
                continue
            
            # Remove dependencies on skipped steps
            deps = [d for d in step_data.get("dependencies", []) if d not in skipped_ids]

            # Auto-fix: get_current_page with no deps must depend on its paired navigate/open step.
            # Pairing: find the navigate step whose index is closest-before this step and not yet
            # claimed by a prior get_current_page — prevents two get_current_page steps both
            # depending on the same (last) navigate when two navigate+read pairs exist.
            if operation == "get_current_page" and not deps:
                nav_ops = {"navigate", "open_page", "open_and_navigate", "fetch_url"}
                all_step_ids = [s["step_id"] for s in plan_data["steps"]]
                current_idx = all_step_ids.index(step_id) if step_id in all_step_ids else len(all_step_ids)
                # Collect navigate steps that appear before this step, in order
                prior_navs = [
                    s["step_id"] for s in plan_data["steps"]
                    if s.get("operation") in nav_ops
                    and s.get("step_id") not in skipped_ids
                    and all_step_ids.index(s["step_id"]) < current_idx
                ]
                # Find which navigate steps are already claimed by earlier get_current_page steps
                claimed = {
                    dep
                    for s in steps  # already-built steps
                    if s.operation == "get_current_page"
                    for dep in s.dependencies
                }
                # Pick the closest unclaimed navigate; fall back to closest claimed if all claimed
                unclaimed = [n for n in reversed(prior_navs) if n not in claimed]
                chosen = unclaimed[0] if unclaimed else (prior_navs[-1] if prior_navs else None)
                if chosen:
                    deps = [chosen]
                    logger.info(f"Auto-paired {step_id} (get_current_page) → {chosen} (navigate)")

            steps.append(TaskStep(
                step_id=step_id,
                description=step_data["description"],
                tool_name=tool_name,
                operation=operation,
                parameters=provided_params,
                domain=step_data.get("domain") or self._infer_domain_for_tool(tool_name, context=plan_data),
                dependencies=deps,
                expected_output=step_data.get("expected_output", ""),
                retry_on_failure=step_data.get("retry_on_failure", True),
                max_retries=step_data.get("max_retries", 3)
            ))
        
        if not steps:
            raise ValueError("No valid steps in plan - all steps were invalid or missing required parameters")

        # Auto-fix: serialize parallel BrowserAutomationTool.navigate steps (shared browser instance)
        # Also ensure take_screenshot steps depend on the last navigate before them
        nav_steps = [
            s for s in steps
            if s.tool_name == "BrowserAutomationTool" and s.operation == "navigate" and not s.dependencies
        ]
        if len(nav_steps) > 1:
            for i in range(1, len(nav_steps)):
                nav_steps[i].dependencies = [nav_steps[i - 1].step_id]
                logger.info(f"Auto-serialized navigate step {nav_steps[i].step_id} → depends on {nav_steps[i-1].step_id} (shared browser)")

        # Auto-fix: take_screenshot must depend on the LAST navigate before it (not just any navigate)
        # This also fixes screenshots that already have a dep on an earlier navigate (stale dep)
        all_step_ids = [s.step_id for s in steps]
        nav_step_ids = {
            s.step_id for s in steps
            if s.tool_name == "BrowserAutomationTool" and s.operation == "navigate"
        }
        for s in steps:
            if s.tool_name == "BrowserAutomationTool" and s.operation == "take_screenshot":
                current_idx = all_step_ids.index(s.step_id)
                prior_navs = [
                    ps.step_id for ps in steps
                    if ps.tool_name == "BrowserAutomationTool" and ps.operation == "navigate"
                    and all_step_ids.index(ps.step_id) < current_idx
                ]
                if prior_navs:
                    last_nav = prior_navs[-1]
                    # Replace deps: keep non-nav deps, ensure last_nav is included
                    non_nav_deps = [d for d in s.dependencies if d not in nav_step_ids]
                    new_deps = non_nav_deps + [last_nav]
                    if new_deps != s.dependencies:
                        logger.info(f"Auto-fixed screenshot {s.step_id} deps: {s.dependencies} → {new_deps}")
                        s.dependencies = new_deps

        self._validate_dependencies(steps)
        
        return ExecutionPlan(
            goal=plan_data["goal"],
            steps=steps,
            estimated_duration=plan_data["estimated_duration"],
            complexity=plan_data["complexity"],
            requires_approval=plan_data.get("requires_approval", False)
        )

    def _normalize_params(self, params: Dict, capability) -> Dict:
        """Remap common LLM param name variants to the real param names."""
        real_names = {p.name for p in capability.parameters}
        aliases = {
            "element_selector": "selector",
            "css_selector": "selector",
            "xpath": "selector",
            "value": "text",
            "input_text": "text",
            "content": "text",
            "javascript": "script",
            "js": "script",
            "code": "script",
        }
        result = dict(params)
        for alias, real in aliases.items():
            if alias in result and alias not in real_names and real in real_names and real not in result:
                result[real] = result.pop(alias)
        return result

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
