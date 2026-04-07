"""Prompt Builder - Constructs LLM prompts for planning."""
import json
from typing import Dict, List, Optional, Any


class PlanningPromptBuilder:
    """Builds prompts for task planning."""

    _OP_ALIASES = {
        "fill_form": "fill_input",
        "fill_form_field": "fill_input",
        "type_text": "fill_input",
        "input_text": "fill_input",
        "enter_text": "fill_input",
        "open_url": "navigate",
        "open_browser": "navigate",
        "go_to": "navigate",
        "goto": "navigate",
        "press_key": "keyboard_action",
        "key_press": "keyboard_action",
        "screenshot": "take_screenshot",
        "get_current_page": "get_page_content",
        "get_page_source": "get_page_content",
        "read_page": "get_page_content",
        "morning_note": "generate_morning_note",
        "morning_brief": "generate_morning_note",
        "full_report": "generate_full_report",
        "advisor_insight": "get_advisor_insight",
    }

    def build_planning_prompt(
        self,
        goal: str,
        tools: Dict,
        skill_context: Optional[Dict] = None,
        past_plans: List = None,
        unified_context: str = "",
    ) -> str:
        """Build main planning prompt."""
        skill_context = skill_context or {}
        skill_name = skill_context.get("skill_name", "")
        planning_profile = skill_context.get("planning_profile", "")
        planning_mode = skill_context.get("planning_mode", "")
        preferred = set(skill_context.get("preferred_tools", []))
        if skill_context.get("include_context_summarizer"):
            preferred.add("ContextSummarizerTool")

        include_past_plans = bool(skill_context.get("include_past_plans", True))
        include_memory_context = bool(skill_context.get("include_memory_context", True))
        include_previous_context = bool(skill_context.get("include_previous_context", True))
        include_adaptive_rules = bool(skill_context.get("include_adaptive_rules", True))
        use_compact_schema = bool(skill_context.get("use_compact_schema", False))

        filtered = {k: v for k, v in tools.items() if k in preferred} if preferred else tools
        if not filtered:
            filtered = tools

        tools_desc = self._build_tool_schema(filtered)
        skill_guidance = self._build_skill_guidance(skill_name, skill_context, preferred)
        parallelism_rules = self._build_parallelism_rules(skill_name)
        example = self._build_skill_example(skill_name)
        past_str = self._build_past_plans_guidance(past_plans or [], preferred) if include_past_plans else ""
        mem_str = self._build_memory_context(
            unified_context if include_memory_context else "",
            skill_context.get("previous_context") if include_previous_context else None,
        )
        viz_hint = self._build_viz_hint(tools)
        goal_guidance = self._build_goal_guidance(goal, skill_name)
        workflow_guidance = self._build_workflow_guidance(skill_name, skill_context)
        planning_mode_guidance = self._build_planning_mode_guidance(planning_mode)
        adaptive_rules = self._build_adaptive_execution_rules(include_adaptive_rules, planning_profile)
        past_section = f"\nPAST APPROACHES (reference only):\n{past_str}\n" if include_past_plans else ""
        memory_section = f"\nMEMORY: {mem_str}{viz_hint}\n" if (include_memory_context or include_previous_context or viz_hint) else ""
        schema = self._build_plan_schema(goal, compact=use_compact_schema)

        return f"""Plan executable steps for this goal.

GOAL: {goal}

SKILL CONTEXT:
{skill_guidance}
{goal_guidance}
{workflow_guidance}
{planning_mode_guidance}

AVAILABLE TOOLS:
{tools_desc}

PARALLELISM RULES:
- dependencies:[] means the step runs immediately (parallel with others)
- Only add a dependency when a step needs the OUTPUT of a prior step
{parallelism_rules}

ADAPTIVE EXECUTION RULES:
{adaptive_rules}

EXAMPLE:
{example}
{past_section}{memory_section}

/no_think

Return ONLY this JSON, no explanation:
{schema}"""

    def _build_goal_guidance(self, goal: str, skill_name: str) -> str:
        """Add goal-specific planning rules for tricky domains."""
        goal_lower = (goal or "").lower()
        if skill_name != "computer_automation":
            return ""

        lines = ["", "GOAL-SPECIFIC RULES:"]

        if any(word in goal_lower for word in ("list", "show", "find", "count", "extract", "read")):
            lines.extend([
                "- For desktop extraction goals, do NOT stop at opening the app or observing the screen.",
                "- Include an interaction step if needed to reach the requested view before extraction.",
                "- End with an explicit extraction-oriented step that returns the requested text or items.",
                "- Prefer ScreenPerceptionTool.extract_text or get_visible_text for final extraction instead of analyze_screen when the goal is to list or read visible items.",
            ])

        if "steam" in goal_lower and "library" in goal_lower:
            lines.extend([
                "- For Steam library tasks, plan to focus Steam, switch to the LIBRARY view, then inspect or extract the visible game titles.",
                "- Prefer InputAutomationTool.smart_click(target=\"Library\", target_app=\"steam\") or another direct interaction before final analysis.",
                "- After the Library view is open, use ScreenPerceptionTool.extract_text(prompt=\"Extract all visible game titles from the Steam library view\", target_app=\"steam\").",
            ])

        lines.extend([
            "- Avoid redundant perception steps. InputAutomationTool.smart_click already performs screen understanding and target localization.",
            "- Do not add capture_screen immediately before infer_visual_state, get_comprehensive_state, or analyze_screen unless a saved screenshot artifact is explicitly needed by a later step.",
            "- When using app-specific UI actions, include a target_app hint when the tool supports it.",
            "- Keep desktop automation inside the main planner DAG. Do not wrap the workflow inside a secondary controller or planner.",
        ])

        return "\n".join(lines)

    def build_replan_prompt(
        self,
        original_goal: str,
        remaining_steps: List,
        completed_summary: Dict,
        completed_artifacts: Dict,
        failed_errors: Dict,
        available_tools: Dict,
    ) -> str:
        """Build replanning prompt."""
        completed_str = json.dumps(completed_summary, indent=2) if completed_summary else "None"
        artifact_str = json.dumps(completed_artifacts, indent=2) if completed_artifacts else "None"
        failed_str = json.dumps(failed_errors, indent=2) if failed_errors else "None"
        remaining_desc = json.dumps(
            [{"step_id": s.step_id, "description": s.description, "tool": s.tool_name, "op": s.operation} for s in remaining_steps],
            indent=2,
        )

        return f"""You are replanning the remaining steps of a task that partially failed.

ORIGINAL GOAL: {original_goal}

COMPLETED STEPS (outputs available):
{completed_str}

COMPLETED STEP ARTIFACTS (reuse these if later steps need actual payloads, text, or structured data):
{artifact_str}

FAILED STEPS (errors):
{failed_str}

ORIGINAL REMAINING STEPS (may need to change):
{remaining_desc}

AVAILABLE TOOLS:
{json.dumps(available_tools, indent=2)}

Generate replacement steps to achieve the original goal given what succeeded.
Use different tools/operations than the ones that failed.
Keep step_ids sequential from the last completed step.
Prefer reusing completed step artifacts over repeating already-successful work.
Add or strengthen `preconditions`, `postconditions`, `checkpoint_policy`, and `retry_policy`
when the failure suggests the executor needs a better readiness check, retry, or checkpoint.

PARALLELISM RULES:
- Steps with "dependencies": [] run IN PARALLEL with other dependency-free steps
- Only add a dependency when a step genuinely needs the OUTPUT of a prior step
- Always ask: "can this step start immediately?" - if yes, leave dependencies empty
- CRITICAL: get_current_page reads the CURRENTLY OPEN browser page - it MUST depend on the navigate/open_page step that loaded the page. Never put get_current_page in dependencies: []

/no_think

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
    "retry_on_failure": true,
    "preconditions": [],
    "postconditions": [],
    "checkpoint_policy": "on_failure",
    "retry_policy": {{}}
  }}
]

Return ONLY valid JSON array, no explanation."""

    def _build_tool_schema(self, tools: Dict) -> str:
        """Build compact tool schema."""
        lines = []
        for tool_name, caps in tools.items():
            lines.append(f"{tool_name}:")
            for cap in caps:
                req = ", ".join(p["name"] for p in cap.get("parameters", []) if p.get("required"))
                opt = ", ".join(f'[{p["name"]}]' for p in cap.get("parameters", []) if not p.get("required"))
                sig = ", ".join(filter(None, [req, opt]))
                desc = cap.get("description", "")[:80]
                lines.append(f"  {cap['name']}({sig})  # {desc}")
        return "\n".join(lines)

    def _build_skill_guidance(self, skill_name: str, skill_context: Dict, preferred: set) -> str:
        """Build skill-specific guidance."""
        lines = []
        if skill_name:
            lines.append(f"Skill: {skill_name} ({skill_context.get('category', '')})")
        if skill_context.get("domain_hint"):
            lines.append(f"User domain hint: {skill_context.get('domain_hint')}")
        if skill_context.get("planning_profile"):
            lines.append(f"Planning profile: {skill_context.get('planning_profile')}")
        if preferred:
            lines.append(f"ONLY USE THESE TOOLS: {', '.join(sorted(preferred))} - do NOT use any other tool")
        if skill_context.get("instructions_summary"):
            lines.append(f"Instructions: {skill_context['instructions_summary'][:200]}")
        if skill_context.get("verification_mode"):
            lines.append(f"Verification: {skill_context['verification_mode']}")
        skill_constraints = [str(item).strip() for item in (skill_context.get("skill_constraints") or []) if str(item).strip()]
        if skill_constraints:
            lines.append("Constraints:")
            for item in skill_constraints[:6]:
                lines.append(f"- {item}")
        return "\n".join(lines) if lines else "No skill selected - use best available tools."

    def _build_workflow_guidance(self, skill_name: str, skill_context: Dict) -> str:
        """Optional workflow hints propagated from skill metadata."""
        hints = skill_context.get("planning_hints") or {}
        workflow_guidance = [
            str(item).strip()
            for item in (skill_context.get("workflow_guidance") or hints.get("workflow_guidance") or [])
            if str(item).strip()
        ]

        lines: List[str] = []
        if skill_name == "computer_automation" and hints.get("observe_act_verify_loop"):
            lines.extend([
                "",
                "DESKTOP WORKFLOW HINTS:",
                "- Build risky desktop flows as Observe -> Act -> Verify waves within the main plan.",
                "- Use ScreenPerceptionTool to ground the next action when the UI state is uncertain.",
                "- After each state-changing action, add either a verification step or strong postconditions before continuing.",
            ])

        if skill_context.get("planning_profile") == "desktop_ui_detail_lookup":
            lines.extend([
                "- This is a named-item detail lookup. Do not plan a broad scan of all visible items if the request only needs one target detail.",
                "- Shape extraction around the user's goal text so the extractor returns the specific named item and requested field/value.",
                "- If the first detail extraction is weak, re-focus the target item or details area instead of scanning the whole screen repeatedly.",
            ])

        if hints.get("vision_mode"):
            lines.append("- Vision mode is enabled for this skill. Prefer visually grounded state checks over assumptions.")
        if hints.get("screenshot_at_each_step"):
            lines.append("- Capture or verify the screen after each meaningful UI transition unless the step already returns grounded visual state.")

        failure_categories = [
            str(item).strip()
            for item in (hints.get("failure_categories") or [])
            if str(item).strip()
        ]
        if failure_categories:
            lines.append(
                f"- When an interaction fails, surface one of these failure categories in replanning context: {', '.join(failure_categories)}."
            )

        for item in (skill_context.get("profile_guidance") or [])[:4]:
            if not item.startswith("- "):
                lines.append(f"- {item}")
            else:
                lines.append(item)

        for item in workflow_guidance[:6]:
            if not item.startswith("- "):
                lines.append(f"- {item}")
            else:
                lines.append(item)

        return "\n".join(lines)

    def _build_planning_mode_guidance(self, planning_mode: str) -> str:
        """Optional deeper-planning guidance for explicit plan-first workflows."""
        mode = str(planning_mode or "").strip().lower()
        if mode != "deep":
            return ""
        return "\n".join([
            "",
            "DEEP PLANNING MODE:",
            "- Decompose the task carefully before choosing tools.",
            "- Surface assumptions through explicit preconditions or verification-oriented steps.",
            "- Prefer plans that are robust to partial failure and easy to resume after approval.",
            "- When multiple approaches exist, choose the one with clearer checkpoints and lower rollback risk.",
        ])

    def _build_parallelism_rules(self, skill_name: str) -> str:
        """Skill-specific parallelism rules."""
        rules = {
            "browser_automation": "- Never run two navigate steps in parallel (shared browser instance)\n- get_page_content MUST depend on the navigate step that loaded the page",
            "computer_automation": "- Prefer direct desktop tools: SystemControlTool, InputAutomationTool, ScreenPerceptionTool\n- Represent retries and verification as normal planner steps or retry policies, not as a nested controller\n- File read/write steps on the same path must be sequential",
            "finance_analysis": "- FinancialAnalysisTool handles everything internally - always use a SINGLE step\n- NEVER use LocalRunNoteTool or LocalCodeSnippetLibraryTool for financial tasks",
        }
        return rules.get(skill_name, "- Steps with no shared outputs can run in parallel")

    def _build_skill_example(self, skill_name: str) -> str:
        """One concrete example per skill."""
        examples = {
            "browser_automation": 'Goal: "search cats on google" ->\n  step_1: navigate(url="https://google.com") deps:[]\n  step_2: fill_input(selector="input[name=q]", text="cats") deps:[step_1]',
            "computer_automation": 'Goal: "open notepad and type hello world" ->\n  step_1: SystemControlTool.launch_application(name="notepad") deps:[]\n  step_2: InputAutomationTool.type_text(text="hello world") deps:[step_1]',
            "finance_analysis": 'Goal: "generate my morning note" ->\n  step_1: FinancialAnalysisTool.generate_morning_note(portfolio_name="main") deps:[]',
        }
        return examples.get(skill_name, "Use the most appropriate tool operation for the goal.")

    def _build_past_plans_guidance(self, past_plans: list, preferred_filter: set = None) -> str:
        """Build past plans context."""
        if not past_plans:
            return "No similar past plans found."
        lines = []
        direct_desktop_tools = {"SystemControlTool", "InputAutomationTool", "ScreenPerceptionTool"}
        for rec in past_plans:
            if preferred_filter:
                plan_tools = {s.get("tool", "") for s in rec.steps[:6]}
                if "ComputerUseController" in plan_tools and plan_tools.intersection(direct_desktop_tools):
                    plan_tools.discard("ComputerUseController")
                if plan_tools and not plan_tools.intersection(preferred_filter):
                    continue
            lines.append(f"- Goal: '{rec.goal_sample}' | Skill: {rec.skill_name} | Win rate: {rec.win_rate():.0%}")
            for s in rec.steps[:6]:
                if (
                    s.get("tool") == "ComputerUseController"
                    and preferred_filter
                    and preferred_filter.intersection(direct_desktop_tools)
                ):
                    continue
                lines.append(f"    {s.get('tool','?')}.{s.get('operation','?')}")
        return "\n".join(lines) if lines else "No relevant past plans found."

    def _build_memory_context(self, unified_context: str, previous_context: Optional[str]) -> str:
        """Build memory context."""
        mem = (unified_context or "").strip()
        if len(mem) > 400:
            mem = mem[:400] + "..."
        prev = f"Previous reply: {previous_context[:200]}\n" if previous_context else ""
        return prev + (mem or "none")

    def _build_adaptive_execution_rules(self, include_full_rules: bool, planning_profile: str) -> str:
        """Build adaptive execution guidance, with a compact variant for simple plans."""
        if include_full_rules:
            return (
                "- When a step depends on external state, loading, eventual consistency, or a UI/page/app being ready, add `preconditions` and `postconditions`.\n"
                "- Use `checkpoint_policy` to tell the executor how cautious to be: `on_failure` by default, `always` for fragile state transitions, `never` only for deterministic local work.\n"
                "- Use `retry_policy` when brief waiting or retrying is better than replanning, for example `{\"strategy\": \"wait_retry\", \"max_attempts\": 3, \"backoff_seconds\": 2}`.\n"
                "- Keep these fields concise and only add them when they materially help execution adapt."
            )

        profile_hint = f" for profile `{planning_profile}`" if planning_profile else ""
        return (
            f"- Keep the plan lean{profile_hint}; only add readiness checks or retry hints when they materially improve execution.\n"
            "- Prefer direct action and extraction steps over defensive boilerplate."
        )

    def _build_plan_schema(self, goal: str, *, compact: bool) -> str:
        """Build the requested planner JSON schema."""
        if compact:
            return f"""{{
  "goal": "{goal}",
  "complexity": "simple|moderate|complex",
  "estimated_duration": <seconds>,
  "requires_approval": false,
  "steps": [
    {{
      "step_id": "step_1",
      "tool_name": "ToolName",
      "operation": "op",
      "parameters": {{}},
      "dependencies": [],
      "expected_output": "...",
      "description": "..."
    }}
  ]
}}

Optional step fields: "domain", "retry_on_failure", "preconditions", "postconditions", "checkpoint_policy", "retry_policy", "max_retries".
Only include optional step fields when they materially help execution."""

        return f"""{{
  "goal": "{goal}",
  "complexity": "simple|moderate|complex",
  "estimated_duration": <seconds>,
  "requires_approval": false,
  "steps": [
    {{
      "step_id": "step_1",
      "tool_name": "ToolName",
      "operation": "op",
      "parameters": {{}},
      "dependencies": [],
      "expected_output": "...",
      "description": "...",
      "domain": "web|computer|development|other",
      "retry_on_failure": true,
      "preconditions": [],
      "postconditions": [],
      "checkpoint_policy": "on_failure",
      "retry_policy": {{}}
    }}
  ]
}}"""

    def _build_viz_hint(self, tools: Dict) -> str:
        """Build visualization hint if tool available."""
        if "DataVisualizationTool" not in tools:
            return ""
        return "\n\nOUTPUT FORMATTING RULE:\n- ALWAYS add a final step using DataVisualizationTool.render_output to format the output.\n- Pass the data from previous steps and a context hint: 'metrics', 'comparison', 'trend', 'distribution', 'table', 'code', 'text', 'health', 'finance'."
