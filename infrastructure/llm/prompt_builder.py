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
        preferred = set(skill_context.get("preferred_tools", []))
        preferred.add("ContextSummarizerTool")

        filtered = {k: v for k, v in tools.items() if k in preferred} if preferred else tools
        if not filtered:
            filtered = tools

        tools_desc = self._build_tool_schema(filtered)
        skill_guidance = self._build_skill_guidance(skill_name, skill_context, preferred)
        parallelism_rules = self._build_parallelism_rules(skill_name)
        example = self._build_skill_example(skill_name)
        past_str = self._build_past_plans_guidance(past_plans or [], preferred)
        mem_str = self._build_memory_context(unified_context, skill_context.get("previous_context"))
        viz_hint = self._build_viz_hint(tools)
        goal_guidance = self._build_goal_guidance(goal, skill_name)

        return f"""Plan executable steps for this goal.

GOAL: {goal}

SKILL CONTEXT:
{skill_guidance}
{goal_guidance}

AVAILABLE TOOLS:
{tools_desc}

PARALLELISM RULES:
- dependencies:[] means the step runs immediately (parallel with others)
- Only add a dependency when a step needs the OUTPUT of a prior step
{parallelism_rules}

ADAPTIVE EXECUTION RULES:
- When a step depends on external state, loading, eventual consistency, or a UI/page/app being ready, add `preconditions` and `postconditions`.
- Use `checkpoint_policy` to tell the executor how cautious to be: `on_failure` by default, `always` for fragile state transitions, `never` only for deterministic local work.
- Use `retry_policy` when brief waiting or retrying is better than replanning, for example `{{"strategy": "wait_retry", "max_attempts": 3, "backoff_seconds": 2}}`.
- Keep these fields concise and only add them when they materially help execution adapt.

EXAMPLE:
{example}

PAST APPROACHES (reference only):
{past_str}

MEMORY: {mem_str}{viz_hint}

/no_think

Return ONLY this JSON, no explanation:
{{
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
        if preferred:
            lines.append(f"ONLY USE THESE TOOLS: {', '.join(sorted(preferred))} - do NOT use any other tool")
        if skill_context.get("instructions_summary"):
            lines.append(f"Instructions: {skill_context['instructions_summary'][:200]}")
        if skill_context.get("verification_mode"):
            lines.append(f"Verification: {skill_context['verification_mode']}")
        return "\n".join(lines) if lines else "No skill selected - use best available tools."

    def _build_parallelism_rules(self, skill_name: str) -> str:
        """Skill-specific parallelism rules."""
        rules = {
            "browser_automation": "- Never run two navigate steps in parallel (shared browser instance)\n- get_page_content MUST depend on the navigate step that loaded the page",
            "computer_automation": "- Prefer direct desktop tools: SystemControlTool, InputAutomationTool, ScreenPerceptionTool\n- Only use ComputerUseController as a compatibility fallback if direct tools cannot express the task\n- File read/write steps on the same path must be sequential",
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

    def _build_viz_hint(self, tools: Dict) -> str:
        """Build visualization hint if tool available."""
        if "DataVisualizationTool" not in tools:
            return ""
        return "\n\nOUTPUT FORMATTING RULE:\n- ALWAYS add a final step using DataVisualizationTool.render_output to format the output.\n- Pass the data from previous steps and a context hint: 'metrics', 'comparison', 'trend', 'distribution', 'table', 'code', 'text', 'health', 'finance'."
