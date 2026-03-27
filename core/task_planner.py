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

            current_tools = {}
            for t in getattr(self.tool_registry, "tools", []):
                current_tools[t.__class__.__name__] = t
                inst = getattr(t, 'name', None)
                if inst and not callable(inst):
                    current_tools[inst] = t
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
            # Use instance name for tools that override .name (e.g. MCPAdapterTool_github)
            instance_name = getattr(tool_instance, 'name', tool_name)
            if callable(instance_name):
                instance_name = tool_name
            if raw_web_tools_hidden and tool_name == "HTTPTool":
                continue
            # Always include MCP adapter tools regardless of skill filter
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
    
    def _build_planning_prompt(self, goal: str, tools: Dict, context: Optional[Dict], past_plans: list = None, unified_context: str = "") -> str:
        """Build a layered planning prompt: goal → skill context → tools → rules → format."""
        skill_context = (context or {}).get("skill_context", {})
        skill_name = skill_context.get("skill_name", "")
        preferred = set(skill_context.get("preferred_tools", []))
        preferred.add("ContextSummarizerTool")

        # ── Layer 1: tool schema — preferred tools only, one line per op ─────
        filtered = {k: v for k, v in tools.items() if k in preferred} if preferred else tools
        if not filtered:
            filtered = tools

        # Hard guard: if skill has preferred tools, NEVER include other tools in the prompt
        # This prevents the LLM from picking LocalRunNoteTool for finance tasks etc.
        if preferred:
            filtered = {k: v for k, v in tools.items() if k in preferred}

        tool_lines = []
        for tool_name, caps in filtered.items():
            tool_lines.append(f"{tool_name}:")
            for cap in caps:
                req = ", ".join(p["name"] for p in cap.get("parameters", []) if p.get("required"))
                opt = ", ".join(f'[{p["name"]}]' for p in cap.get("parameters", []) if not p.get("required"))
                sig = ", ".join(filter(None, [req, opt]))
                desc = cap.get("description", "")[:80]
                tool_lines.append(f"  {cap['name']}({sig})  # {desc}")
        tools_desc = "\n".join(tool_lines)

        # ── Layer 2: skill guidance — what this skill expects ─────────────────
        skill_lines = []
        if skill_name:
            skill_lines.append(f"Skill: {skill_name} ({skill_context.get('category', '')})")
        if preferred:
            skill_lines.append(f"ONLY USE THESE TOOLS: {', '.join(sorted(preferred))} — do NOT use any other tool")
        if skill_context.get("instructions_summary"):
            skill_lines.append(f"Instructions: {skill_context['instructions_summary'][:200]}")
        if skill_context.get("verification_mode"):
            skill_lines.append(f"Verification: {skill_context['verification_mode']}")
        if skill_context.get("output_types"):
            skill_lines.append(f"Expected outputs: {', '.join(skill_context['output_types'])}")
        if skill_context.get("required_tools"):
            skill_lines.append(f"Required tools: {', '.join(skill_context['required_tools'])}")
        if skill_context.get("skill_constraints"):
            skill_lines.append(f"Constraints: {'; '.join(skill_context['skill_constraints'])}")
        skill_guidance = "\n".join(skill_lines) if skill_lines else "No skill selected — use best available tools."

        # ── Layer 3: parallelism rules — skill-specific only ──────────────────
        parallelism_rules = self._build_parallelism_rules(skill_name)

        # ── Layer 4: one concrete example for this skill ──────────────────────
        example = self._build_skill_example_compact(skill_name)

        # ── Layer 5: past plans — compact, capped ─────────────────────────────
        # Filter past plans to only show steps using preferred tools
        past_str = self._build_past_plans_guidance(past_plans or [], preferred_filter=preferred)

        # ── Layer 6: memory — hard cap 400 chars ──────────────────────────────
        mem = (unified_context or "").strip()
        if len(mem) > 400:
            mem = mem[:400] + "..."
        prev_ctx = (context or {}).get("previous_context", "")
        mem_str = (f"Previous reply: {prev_ctx[:200]}\n" if prev_ctx else "") + (mem or "none")

        # Check if DataVisualizationTool is available
        has_viz = "DataVisualizationTool" in tools
        viz_hint = (
            "\n\nOUTPUT FORMATTING RULE:\n"
            "- ALWAYS add a final step using DataVisualizationTool.render_output to format the output.\n"
            "- Pass the data from previous steps and a context hint: 'metrics', 'comparison', 'trend', 'distribution', 'table', 'code', 'text', 'health', 'finance'.\n"
            "- This automatically chooses the best visualization (chart, table, metrics cards, formatted text, etc.).\n"
            "- Example: DataVisualizationTool.render_output(data='{previous_step_output}', context='metrics', title='System Health')\n"
            "- For charts specifically, use context='trend' for line charts, 'comparison' for bar charts, 'distribution' for pie charts."
        ) if has_viz else ""

        return f"""Plan executable steps for this goal.

GOAL: {goal}

SKILL CONTEXT:
{skill_guidance}

AVAILABLE TOOLS:
{tools_desc}

PARALLELISM RULES:
- dependencies:[] means the step runs immediately (parallel with others)
- Only add a dependency when a step needs the OUTPUT of a prior step
{parallelism_rules}

EXAMPLE:
{example}

PAST APPROACHES (reference only):
{past_str}

MEMORY: {mem_str}{viz_hint}

Return ONLY this JSON, no explanation:
{{
  "goal": "{goal}",
  "complexity": "simple|moderate|complex",
  "estimated_duration": <seconds>,
  "requires_approval": false,
  "steps": [
    {{"step_id": "step_1", "tool_name": "ToolName", "operation": "op", "parameters": {{}}, "dependencies": [], "expected_output": "...", "description": "...", "domain": "web|computer|development|other", "retry_on_failure": true}}
  ]
}}"""

    def _build_parallelism_rules(self, skill_name: str) -> str:
        """Return skill-specific parallelism rules — only what's relevant."""
        rules = {
            "browser_automation": (
                "- Never run two navigate steps in parallel (shared browser instance)\n"
                "- get_page_content MUST depend on the navigate step that loaded the page\n"
                "- take_screenshot MUST depend on the last navigate before it"
            ),
            "computer_automation": (
                "- File read/write steps on the same path must be sequential"
            ),
            "finance_analysis": (
                "- FinancialAnalysisTool handles everything internally — always use a SINGLE step\n"
                "- generate_morning_note: use for 'morning note', 'morning brief', 'market brief', 'daily brief'\n"
                "- generate_full_report: use for 'full report', 'investment report', 'portfolio report'\n"
                "- get_advisor_insight: use for portfolio questions, stock analysis, 'how am I doing'\n"
                "- save_portfolio: use for 'save my portfolio', 'update my portfolio'\n"
                "- NEVER use LocalRunNoteTool or LocalCodeSnippetLibraryTool for financial tasks"
            ),
        }
        return rules.get(skill_name, "- Steps with no shared outputs can run in parallel")

    def _build_skill_example_compact(self, skill_name: str) -> str:
        """One concrete step-flow example per skill."""
        examples = {
            "browser_automation": (
                'Goal: "search cats on google" →\n'
                '  step_1: navigate(url="https://google.com") deps:[]\n'
                '  step_2: fill_input(selector="input[name=q]", text="cats") deps:[step_1]\n'
                '  step_3: click_element(selector="input[type=submit]") deps:[step_2]'
            ),
            "computer_automation": (
                'Goal: "read config.yaml" →\n'
                '  step_1: read_file(path="config.yaml") deps:[]'
            ),
            "code_workspace": (
                'Goal: "run tests" →\n'
                '  step_1: execute(command="pytest -q") deps:[]'
            ),
            "data_operations": (
                'Goal: "query tool logs" →\n'
                '  step_1: query_logs(limit=20) deps:[]'
            ),
            "knowledge_management": (
                'Goal: "save auth snippet" →\n'
                '  step_1: save_snippet(name="auth", code="...", language="python") deps:[]'
            ),
            "finance_analysis": (
                'Goal: "generate my morning note" →\n'
                '  step_1: FinancialAnalysisTool.generate_morning_note(portfolio_name="main") deps:[]\n'
                'Goal: "generate full report" →\n'
                '  step_1: FinancialAnalysisTool.generate_full_report(portfolio_name="main") deps:[]\n'
                'Goal: "how is AAPL doing" →\n'
                '  step_1: FinancialAnalysisTool.get_advisor_insight(holdings={"AAPL": 1}, question="how is AAPL doing") deps:[]\n'
                'Goal: "how is nifty doing" →\n'
                '  step_1: FinancialAnalysisTool.get_advisor_insight(holdings={"^NSEI": 1}, question="how is nifty doing today") deps:[]'
            ),
            "web_research": (
                '(web_research is handled by WebResearchAgent — single step: search_web or fetch_url)'
            ),
        }
        return examples.get(skill_name, 'Use the most appropriate tool operation for the goal.')

    def _build_past_plans_guidance(self, past_plans: list, preferred_filter: set = None) -> str:
        if not past_plans:
            return "No similar past plans found."
        lines = []
        for rec in past_plans:
            if preferred_filter:
                plan_tools = {s.get("tool", "") for s in rec.steps[:6]}
                if plan_tools and not plan_tools.intersection(preferred_filter):
                    continue
            lines.append(
                f"- Goal: '{rec.goal_sample}' | Skill: {rec.skill_name} "
                f"| Win rate: {rec.win_rate():.0%} ({rec.success_count}✓/{rec.fail_count}✗) "
                f"| Avg duration: {rec.avg_duration_s:.1f}s"
            )
            for s in rec.steps[:6]:  # cap at 6 steps to keep prompt tight
                lines.append(f"    {s.get('tool','?')}.{s.get('operation','?')} [{s.get('domain','')}]")
        return "\n".join(lines) if lines else "No relevant past plans found."

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
        "get_current_page": "get_page_content",
        "get_page_source": "get_page_content",
        "read_page": "get_page_content",
        "get_page_text": "get_page_content",
        # finance aliases
        "morning_note": "generate_morning_note",
        "morning_notes": "generate_morning_note",
        "morning_brief": "generate_morning_note",
        "market_brief": "generate_morning_note",
        "daily_brief": "generate_morning_note",
        "full_report": "generate_full_report",
        "investment_report": "generate_full_report",
        "portfolio_report": "generate_full_report",
        "advisor_insight": "get_advisor_insight",
        "portfolio_analysis": "get_portfolio_analysis",
    }

    def _validate_plan(self, plan_data: Dict, original_goal: str) -> ExecutionPlan:
        """Validate and convert plan data to ExecutionPlan."""
        required = ["goal", "steps", "complexity", "estimated_duration"]
        for field in required:
            if field not in plan_data:
                raise ValueError(f"Missing required field: {field}")
        
        current_tools = {}
        for tool in getattr(self.tool_registry, 'tools', []):
            # Index by both class name and instance name so MCP tools are found
            current_tools[tool.__class__.__name__] = tool
            inst = getattr(tool, 'name', None)
            if inst and not callable(inst):
                current_tools[inst] = tool
        
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
            
            # If ALL dependencies were skipped, skip this step too (dead reference cascade)
            raw_deps = step_data.get("dependencies", [])
            if raw_deps and all(d in skipped_ids for d in raw_deps):
                logger.warning(f"Step {step_id} all dependencies skipped, cascading skip")
                skipped_ids.add(step_id)
                continue
            # Remove dependencies on skipped steps
            deps = [d for d in raw_deps if d not in skipped_ids]

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
