"""Autonomous Agent - Self-directed goal achievement with planning and execution."""
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from application.use_cases.planning.task_planner import TaskPlanner, ExecutionPlan
from application.use_cases.execution.execution_engine import ExecutionEngine, ExecutionState, StepStatus
from infrastructure.persistence.file_storage.memory_system import MemorySystem
from application.services.skill_selector import SkillSelector
from application.services.skill_context_hydrator import SkillContextHydrator
from domain.entities.skill_models import SkillSelection as SkillSelectionModel

logger = logging.getLogger(__name__)


@dataclass
class AgentGoal:
    """Goal for autonomous agent."""
    goal_text: str
    success_criteria: List[str]
    max_iterations: int = 3
    require_approval: bool = False


class AutonomousAgent:
    """
    Autonomous agent that can:
    1. Break down goals into plans
    2. Execute plans step-by-step
    3. Verify results against success criteria
    4. Iterate and self-correct on failures
    """
    
    def __init__(
        self,
        task_planner: TaskPlanner,
        execution_engine: ExecutionEngine,
        memory_system: MemorySystem,
        llm_client,
        skill_registry=None,
        skill_selector: Optional[SkillSelector] = None,
    ):
        self.planner = task_planner
        self.executor = execution_engine
        self.memory = memory_system
        self.llm_client = llm_client
        self.skill_registry = skill_registry
        self.skill_selector = skill_selector or SkillSelector()
        from infrastructure.persistence.file_storage.strategic_memory import get_strategic_memory
        self.strategic_memory = get_strategic_memory()
    
    def achieve_goal(
        self,
        goal: AgentGoal,
        session_id: str,
        context: Optional[Dict] = None,
        stop_check=None
    ) -> Dict[str, Any]:
        """
        Autonomously work toward achieving a goal.
        
        Returns:
            Result dict with success status, iterations, and final state
        """
        logger.info(f"[AGENT] Starting goal: '{goal.goal_text[:80]}'")

        if not goal.success_criteria:
            goal.success_criteria = self._derive_success_criteria(goal.goal_text, context)

        # Reactive loop for web/browser tasks
        skill_name = (context or {}).get("skill_context", {}).get("skill_name", "")
        if skill_name in ("web_research", "browser_automation"):
            from application.use_cases.chat.web_research_agent import WebResearchAgent
            conv_history = (context or {}).get("conversation_history", [])
            return WebResearchAgent(
                self.llm_client,
                self.executor.tool_registry if hasattr(self.executor, 'tool_registry') else None,
                orchestrator=getattr(self.executor, "tool_orchestrator", None),
            ).run(goal.goal_text, session_id, conversation_history=conv_history)
        

        # Set active goal in memory
        self.memory.set_active_goal(session_id, goal.goal_text)
        
        # Add system message
        self.memory.add_message(
            session_id,
            "system",
            f"Starting autonomous goal: {goal.goal_text}"
        )
        
        iteration = 0
        success = False
        final_state = None
        execution_history = []
        tool_history = []
        
        while iteration < goal.max_iterations and not success:
            iteration += 1
            if stop_check and stop_check():
                logger.info("[AGENT] Stop requested — aborting")
                return {
                    "success": False,
                    "iterations": iteration,
                    "execution_history": execution_history,
                    "final_state": final_state,
                    "goal": goal.goal_text,
                    "message": "Stopped by user",
                    "status": "stopped",
                }
            logger.info(f"[AGENT] Iteration {iteration}/{goal.max_iterations}")
            
            try:
                # Step 1: Plan
                plan = self._plan_iteration(goal, session_id, context, iteration)
                
                if not plan:
                    logger.error("Planning failed")
                    break
                
                # Check if approval needed
                if goal.require_approval or plan.requires_approval:
                    logger.info("Plan requires approval - pausing")
                    return {
                        "success": False,
                        "status": "awaiting_approval",
                        "plan": plan,
                        "iteration": iteration,
                        "message": "Plan requires user approval"
                    }
                
                # Step 2: Execute
                import time as _time
                execution_id = f"{session_id}_iter{iteration}"
                exec_start = _time.time()

                # Emit plan to UI
                from infrastructure.messaging.event_bus import get_event_bus
                _bus = get_event_bus()
                _bus.emit_sync("agent_plan", {
                    "iteration": iteration,
                    "max_iterations": goal.max_iterations,
                    "steps": [
                        {
                            "step_id": s.step_id,
                            "description": s.description,
                            "tool_name": s.tool_name,
                            "operation": s.operation,
                            "status": "pending",
                        }
                        for s in plan.steps
                    ],
                })

                execution_skill_context = self._build_execution_skill_context(goal, context)
                state = self.executor.execute_plan(
                    plan,
                    execution_id,
                    skill_context=execution_skill_context,
                    session_id=session_id,
                )
                exec_duration = _time.time() - exec_start
                execution_history.append(execution_id)
                final_state = state
                tool_history.extend(self._build_tool_history(plan, state))

                # Link execution to session
                self.memory.add_execution(session_id, execution_id)

                # Step 3: Verify
                verification = self._verify_results(goal, state, session_id)

                # Shared data for strategic memory recording
                _skill_name = (context or {}).get("skill_context", {}).get("skill_name", "")
                _plan_steps = [
                    {"tool_name": s.tool_name, "operation": s.operation, "domain": s.domain}
                    for s in plan.steps
                ]

                if verification["success"]:
                    success = True
                    self.strategic_memory.record(
                        goal=goal.goal_text, skill_name=_skill_name,
                        steps=_plan_steps, success=True, duration_s=exec_duration,
                    )
                    logger.info(f"[AGENT] Goal achieved in {iteration} iteration(s)")
                    break

                # Step 4: Analyze failure and prepare for retry
                if iteration < goal.max_iterations:
                    self.strategic_memory.record(
                        goal=goal.goal_text, skill_name=_skill_name,
                        steps=_plan_steps, success=False, duration_s=exec_duration,
                    )
                    self._analyze_failure(goal, state, verification, session_id)
                    context = self._update_context_for_retry(context, state, verification)
                
            except Exception as e:
                logger.error(f"Iteration {iteration} failed: {e}")
                self.memory.add_message(
                    session_id,
                    "system",
                    f"Iteration {iteration} error: {str(e)}"
                )
                break
        
        # Final result
        result = {
            "success": success,
            "iterations": iteration,
            "execution_history": execution_history,
            "final_state": final_state,
            "tool_history": tool_history,
            "goal": goal.goal_text
        }
        
        if success:
            result["message"] = f"Goal achieved in {iteration} iterations"
            self.memory.add_message(
                session_id,
                "system",
                f"✓ Goal achieved: {goal.goal_text}"
            )
        else:
            result["message"] = f"Goal not achieved after {iteration} iterations"
            self.memory.add_message(
                session_id,
                "system",
                f"✗ Goal failed: {goal.goal_text}"
            )
        
        # Clear active goal
        self.memory.set_active_goal(session_id, None)
        
        return result

    def _build_execution_skill_context(self, goal: AgentGoal, context: Optional[Dict[str, Any]]):
        """Materialize a SkillExecutionContext for runtime execution from planner context."""
        skill_context_data = dict((context or {}).get("skill_context") or {})
        skill_name = str(skill_context_data.get("skill_name", "") or "").strip()
        if not skill_name or not self.skill_registry:
            return None

        skill_def = self.skill_registry.get(skill_name)
        if not skill_def:
            return None

        selection = SkillSelectionModel(
            matched=True,
            skill_name=skill_name,
            category=str(skill_context_data.get("category", "") or ""),
            confidence=float(skill_context_data.get("confidence", 1.0) or 1.0),
            reason=str(skill_context_data.get("reason", "") or ""),
        )
        execution_context = SkillContextHydrator.build_context(selection, skill_def, goal.goal_text)

        if skill_context_data.get("instructions_summary"):
            execution_context.instructions_summary = str(skill_context_data["instructions_summary"])
        if skill_context_data.get("preferred_tools"):
            execution_context.preferred_tools = list(skill_context_data["preferred_tools"])
        if skill_context_data.get("verification_mode"):
            execution_context.verification_mode = str(skill_context_data["verification_mode"])
        if skill_context_data.get("output_types"):
            execution_context.expected_output_types = list(skill_context_data["output_types"])

        merged_hints = dict(getattr(execution_context, "planning_hints", {}) or {})
        merged_hints.update(dict(skill_context_data.get("planning_hints") or {}))
        if skill_context_data.get("planning_profile"):
            merged_hints["planning_profile"] = skill_context_data["planning_profile"]
            setattr(execution_context, "planning_profile", skill_context_data["planning_profile"])
        if skill_context_data.get("domain_hint"):
            merged_hints["domain_hint"] = skill_context_data["domain_hint"]
        execution_context.planning_hints = merged_hints

        execution_context.validation_rules.update({
            "planning_profile": skill_context_data.get("planning_profile"),
            "domain_hint": skill_context_data.get("domain_hint"),
            "include_past_plans": skill_context_data.get("include_past_plans"),
            "include_memory_context": skill_context_data.get("include_memory_context"),
            "include_previous_context": skill_context_data.get("include_previous_context"),
            "use_compact_schema": skill_context_data.get("use_compact_schema"),
        })
        return execution_context

    def _build_tool_history(self, plan: ExecutionPlan, state: ExecutionState) -> List[Dict[str, Any]]:
        """Flatten an execution state into tool usage telemetry."""
        registry = getattr(state, "state_registry", None)
        if registry is not None:
            history = registry.build_tool_history()
            if history:
                return history

        step_map = {step.step_id: step for step in plan.steps}
        history: List[Dict[str, Any]] = []

        for step_id, step_result in state.step_results.items():
            step = step_map.get(step_id)
            if not step:
                continue
            status = getattr(step_result.status, "value", str(step_result.status))
            history.append({
                "tool": step.tool_name,
                "operation": step.operation,
                "success": status == StepStatus.COMPLETED.value,
                "data": getattr(step_result, "output", None),
                "error": getattr(step_result, "error", None),
                "execution_time": getattr(step_result, "execution_time", 0.0),
            })

        return history
    
    def _plan_iteration(
        self,
        goal: AgentGoal,
        session_id: str,
        context: Optional[Dict],
        iteration: int
    ) -> Optional[ExecutionPlan]:
        """Plan for current iteration."""
        logger.info(f"[AGENT] Planning iteration {iteration}")
        
        # Get conversation context
        conv_summary = self.memory.get_conversation_summary(session_id)
        
        # Enhance context with memory
        enhanced_context = context or {}
        enhanced_context["conversation_summary"] = conv_summary
        enhanced_context["iteration"] = iteration

        if self.skill_registry and not (context or {}).get("skill_context"):
            selection = self.skill_selector.select_skill(goal.goal_text, self.skill_registry, self.llm_client)
            if selection.matched and selection.skill_name:
                skill = self.skill_registry.get(selection.skill_name)
                if skill:
                    # Build skill context using hydrator
                    skill_context = SkillContextHydrator.build_context(selection, skill, goal.goal_text)
                    enhanced_context["skill_selection"] = {
                        "matched": True,
                        "skill_name": selection.skill_name,
                        "category": selection.category,
                        "confidence": selection.confidence,
                        "reason": selection.reason,
                    }
                    enhanced_context["skill_context"] = {
                        "skill_name": skill_context.skill_name,
                        "category": skill_context.category,
                        "instructions_summary": getattr(skill_context, "instructions_summary", ""),
                        "preferred_tools": list(skill_context.preferred_tools),
                        "required_tools": getattr(skill_context.skill_definition, 'required_tools', []),
                        "verification_mode": skill_context.verification_mode,
                        "output_types": list(skill_context.expected_output_types),
                        "ui_renderer": getattr(skill_context.skill_definition, 'ui_renderer', ''),
                        "skill_constraints": list(
                            (getattr(skill_context, "planning_hints", {}) or {}).get("skill_constraints", [])
                        ),
                        "workflow_guidance": list(
                            (getattr(skill_context, "planning_hints", {}) or {}).get("workflow_guidance", [])
                        ),
                        "planning_hints": dict(getattr(skill_context, "planning_hints", {}) or {}),
                    }

        # Add learned patterns
        similar_patterns = self.memory.get_patterns("successful_goals", limit=3)
        if similar_patterns:
            enhanced_context["similar_successful_approaches"] = similar_patterns

        # Inject failed attempts so the planner avoids repeating the same mistakes
        if iteration > 1:
            failed_patterns = self.memory.get_patterns("failed_attempts", limit=3)
            if failed_patterns:
                enhanced_context["previously_failed_approaches"] = failed_patterns
        
        try:
            plan = self.planner.plan_task(goal.goal_text, enhanced_context)
            
            # Log plan
            self.memory.add_message(
                session_id,
                "system",
                f"Generated plan with {len(plan.steps)} steps"
            )
            
            return plan
            
        except Exception as e:
            if self._is_perception_only_planning_failure(e):
                retry_context = self._build_desktop_replan_context(enhanced_context, goal.goal_text)
                try:
                    logger.info("[AGENT] Retrying planning with desktop extraction guidance")
                    self.memory.add_message(
                        session_id,
                        "system",
                        "Planning retry: adding desktop interaction and extraction guidance"
                    )
                    plan = self.planner.plan_task(goal.goal_text, retry_context)
                    self.memory.add_message(
                        session_id,
                        "system",
                        f"Generated revised plan with {len(plan.steps)} steps"
                    )
                    return plan
                except Exception as retry_error:
                    logger.error(f"Planning retry failed: {retry_error}")
                    self.memory.add_message(
                        session_id,
                        "system",
                        f"Planning retry error: {str(retry_error)}"
                    )
            logger.error(f"Planning failed: {e}")
            self.memory.add_message(
                session_id,
                "system",
                f"Planning error: {str(e)}"
            )
            return None
    
    def _verify_results(
        self,
        goal: AgentGoal,
        state: ExecutionState,
        session_id: str
    ) -> Dict[str, Any]:
        """Verify if execution achieved the goal."""
        logger.info(f"[AGENT] Verifying execution results")
        
        # Check if all steps completed
        completed_steps = [
            r for r in state.step_results.values()
            if r.status == StepStatus.COMPLETED
        ]
        
        failed_steps = [
            r for r in state.step_results.values()
            if r.status == StepStatus.FAILED
        ]
        
        # Basic verification
        if failed_steps:
            return {
                "success": False,
                "reason": f"{len(failed_steps)} steps failed",
                "failed_steps": [s.step_id for s in failed_steps],
                "failed_details": {s.step_id: s.error for s in failed_steps}
            }
        
        # Use LLM to verify against success criteria with structured JSON response
        if goal.success_criteria:
            verification_prompt = self._build_verification_prompt(
                goal,
                state,
                session_id
            )
            
            try:
                response = self.llm_client._call_llm(
                    verification_prompt,
                    temperature=0.1,
                    expect_json=True
                )

                if not response:
                    return {"success": len(completed_steps) == len(state.step_results), "reason": "All steps completed"}

                # Parse JSON response
                import json
                try:
                    result = json.loads(response) if isinstance(response, str) else response
                    parsed = {
                        "success": result.get("success", False),
                        "reason": result.get("reason", "Unknown"),
                        "details": result.get("details", ""),
                        "missing_parts": result.get("missing_parts", [])
                    }
                    if not parsed["success"]:
                        heuristic = self._heuristic_goal_check(goal, state, completed_steps)
                        if heuristic.get("success") and self._looks_like_truncation_failure(parsed):
                            heuristic["reason"] = "Heuristic override: execution evidence satisfies success criteria"
                            heuristic["details"] = parsed.get("details") or parsed.get("reason", "")
                            return heuristic
                    return parsed
                except json.JSONDecodeError:
                    # Fallback to keyword matching if JSON parsing fails
                    logger.warning("Failed to parse verification JSON, using fallback")
                    if "\"success\": true" in response.lower() or "'success': true" in response.lower():
                        return {"success": True, "reason": "Success criteria met"}
                    else:
                        return {
                            "success": False,
                            "reason": "Success criteria not met",
                            "details": response
                        }
                    
            except Exception as e:
                logger.error(f"LLM verification failed: {e}")
                return self._heuristic_goal_check(goal, state, completed_steps)

        return self._heuristic_goal_check(goal, state, completed_steps)
    
    def _build_verification_prompt(
        self,
        goal: AgentGoal,
        state: ExecutionState,
        session_id: str
    ) -> str:
        """Build prompt for LLM to verify goal achievement."""
        registry = getattr(state, "state_registry", None)
        completed_artifacts = {}
        latest_world_state = {}
        if registry is not None:
            completed_artifacts = registry.build_completed_artifacts(max_chars=1200)
            latest_world_state = registry.latest_world_state()
        # Get step results summary
        results_summary = []
        for step_id, result in state.step_results.items():
            out = self._format_verification_output(result.output)
            if step_id in completed_artifacts:
                out = completed_artifacts[step_id].get("output", "none")
            feedback = (result.meta or {}).get("execution_feedback") or {}
            feedback_note = ""
            if feedback.get("recommended_action") and feedback.get("recommended_action") != "continue":
                feedback_note = (
                    f" | feedback={feedback.get('recommended_action')}"
                    f" ({feedback.get('blocking_reason', 'no reason')})"
                )
            results_summary.append(f"- {step_id}: {result.status.value} - {out}{feedback_note}")
        
        return f"""Verify if the ENTIRE goal was achieved based on execution results.

GOAL: {goal.goal_text}

SUCCESS CRITERIA:
{chr(10).join(f"- {c}" for c in goal.success_criteria)}

EXECUTION RESULTS:
{chr(10).join(results_summary)}

LATEST WORLD STATE:
{latest_world_state or "none"}

CRITICAL: Check if ALL parts of the goal were completed:
1. Break down the goal into individual sub-tasks
2. Verify EACH sub-task was completed in the execution results
3. Only respond SUCCESS if EVERY part of the goal is done
4. Prioritize the explicit SUCCESS CRITERIA above impossible literal interpretations of the original wording
5. Do not mark FAILURE only because a list looks partial or truncated if the success criteria were satisfied with explicit extracted items from the correct app/view

For example, if goal is "Go to Google, search Wikipedia, then go to Wikipedia and search AGI":
- Must verify: Went to Google ✓
- Must verify: Searched for Wikipedia ✓
- Must verify: Navigated to Wikipedia ✓
- Must verify: Searched for AGI on Wikipedia ✓

If ANY part is missing, respond FAILURE.

Respond with ONLY valid JSON in this format:
{{
  "success": true/false,
  "reason": "brief explanation",
  "details": "detailed analysis",
  "missing_parts": ["list of incomplete parts if any"]
}}
"""

    def _derive_success_criteria(self, goal_text: str, context: Optional[Dict[str, Any]]) -> List[str]:
        """Generate minimal goal-specific success criteria when callers provide none."""
        goal_lower = (goal_text or "").lower()
        criteria: List[str] = []
        skill_name = ((context or {}).get("skill_context") or {}).get("skill_name", "")

        if any(word in goal_lower for word in ("open ", "launch ", "start ")):
            criteria.append("The target application or destination must actually be opened and focused.")

        if "steam" in goal_lower and "library" in goal_lower:
            criteria.append("Steam must be on the LIBRARY view, not just the STORE page.")

        if any(word in goal_lower for word in ("list", "show", "find", "count", "extract", "read")):
            criteria.append("The final result must include explicit extracted data answering the request, not just a screenshot or visual analysis.")

        if "games" in goal_lower:
            criteria.append("Visible game titles must be extracted as text in the final outputs.")

        if not criteria and skill_name == "computer_automation":
            criteria.append("The requested desktop task must be completed end-to-end, not only observed.")

        return criteria

    def _heuristic_goal_check(
        self,
        goal: AgentGoal,
        state: ExecutionState,
        completed_steps: List[Any],
    ) -> Dict[str, Any]:
        """Stricter non-LLM fallback verification for actionable desktop requests."""
        unfinished = [
            result for result in state.step_results.values()
            if result.status not in (StepStatus.COMPLETED, StepStatus.SKIPPED)
        ]
        if unfinished:
            return {"success": False, "reason": "Some steps incomplete"}

        goal_lower = (goal.goal_text or "").lower()
        outputs = [getattr(result, "output", None) for result in state.step_results.values()]
        output_text = " ".join(str(output)[:500] for output in outputs if output is not None).lower()

        def _contains_explicit_list_data() -> bool:
            for output in outputs:
                explicit_items = self._extract_explicit_items(output)
                if self._looks_like_quality_item_list(explicit_items, goal_lower):
                    return True
                if not isinstance(output, dict):
                    continue
                analysis = str(output.get("analysis", "") or "").strip()
                if analysis and self._looks_like_explicit_text_list(analysis, goal_lower):
                    return True
            return False

        if "steam" in goal_lower and "library" in goal_lower:
            on_library_view = any(
                isinstance(output, dict)
                and isinstance(output.get("visual_state"), dict)
                and str(output["visual_state"].get("current_view", "")).lower() == "library"
                for output in outputs
            )
            clicked_library = any(
                isinstance(output, dict)
                and (
                    str(output.get("target", "")).lower() == "library"
                    or str((output.get("matched_element") or {}).get("label", "")).lower() == "library"
                    or str((output.get("matched_element") or {}).get("text", "")).lower() == "library"
                )
                for output in outputs
            )
            if not on_library_view and not (clicked_library and _contains_explicit_list_data()):
                return {"success": False, "reason": "Steam library view was not reached", "missing_parts": ["open the library view"]}

        if any(word in goal_lower for word in ("list", "show", "find", "count", "extract", "read")):
            if not _contains_explicit_list_data():
                evidence_outputs = [
                    output for output in outputs
                    if isinstance(output, dict)
                    and (
                        output.get("answer_ready") is True
                        or (
                            output.get("requested_field")
                            and output.get("field_value")
                            and not output.get("ambiguous", False)
                        )
                    )
                ]
                if evidence_outputs:
                    return {"success": True, "reason": "Structured evidence satisfied the requested desktop detail lookup"}
                return {
                    "success": False,
                    "reason": "Requested explicit data was not extracted",
                    "missing_parts": ["extract and return the requested items as text or structured data"],
                    "details": output_text[:500],
                }

        return {"success": True, "reason": "Success criteria satisfied by heuristic verification"}

    def _looks_like_explicit_text_list(self, text: str, goal_lower: str) -> bool:
        """Accept plain-text extraction when it clearly contains the requested items."""
        normalized = text.strip()
        if len(normalized) < 20:
            return False
        lower = normalized.lower()
        if any(phrase in lower for phrase in ("unable to determine", "cannot determine", "not visible", "store page")):
            return False

        separators = ("\n- ", "\n* ", "\n1.", ", ")
        has_list_shape = any(sep in normalized for sep in separators)
        mentions_items = any(word in lower for word in ("title", "titles", "games", "library"))
        return has_list_shape or mentions_items

    def _extract_explicit_items(self, output: Any) -> List[str]:
        """Pull candidate extracted items from common structured tool outputs."""
        if not isinstance(output, dict):
            return []

        for key in ("games", "items", "results", "titles", "entries", "data"):
            value = output.get(key)
            if isinstance(value, list):
                return [str(item).strip() for item in value if str(item).strip()]
        return []

    def _looks_like_quality_item_list(self, items: List[str], goal_lower: str) -> bool:
        """Reject obviously noisy extraction output when verifying completion."""
        if not items:
            return False

        blocked_fragments = (
            "forge", "repo", "remote", "tunnels", "terminal", "extensions",
            "search", "downloads", "friends", "community", "store", "library",
            "agent", "steam",
        )
        quality = []
        for item in items:
            lower = item.lower()
            if len(item.strip()) < 3:
                continue
            if any(fragment in lower for fragment in blocked_fragments):
                continue
            if sum(ch.isalpha() for ch in item) < 3:
                continue
            quality.append(item)

        if any(word in goal_lower for word in ("game", "steam", "library")):
            return len(quality) >= 2
        return bool(quality)

    def _format_verification_output(self, output: Any, max_chars: int = 1200) -> str:
        """Serialize step output without aggressively truncating the evidence."""
        if output is None:
            return "none"
        try:
            import json
            if isinstance(output, (dict, list)):
                text = json.dumps(output, ensure_ascii=True, default=str)
            else:
                text = str(output)
        except Exception:
            text = str(output)
        return text[:max_chars] + ("..." if len(text) > max_chars else "")

    def _looks_like_truncation_failure(self, verification: Dict[str, Any]) -> bool:
        """Detect false negatives caused by the verifier complaining about cut-off evidence."""
        combined = " ".join(
            str(verification.get(field, "") or "")
            for field in ("reason", "details")
        ).lower()
        markers = (
            "cut off",
            "cutoff",
            "truncat",
            "partial",
            "mid-word",
            "incomplete",
        )
        return any(marker in combined for marker in markers)

    def _is_perception_only_planning_failure(self, error: Exception) -> bool:
        """Detect the specific desktop planning guard we want to recover from."""
        return "perception-only flow" in str(error).lower()

    def _build_desktop_replan_context(
        self,
        context: Optional[Dict[str, Any]],
        goal_text: str,
    ) -> Dict[str, Any]:
        """Add sharper instructions for desktop extraction replanning."""
        retry_context = dict(context or {})
        skill_context = dict(retry_context.get("skill_context") or {})
        instructions = str(skill_context.get("instructions_summary", "")).strip()
        guidance = (
            " For desktop extraction requests, include a navigation step to the requested app view, "
            "then an interaction step if needed, then a final extraction step that returns the requested "
            "text or items. Do not stop at screenshot capture or screen analysis alone."
        )
        if "steam" in (goal_text or "").lower() and "library" in (goal_text or "").lower():
            guidance += (
                " For Steam library requests, explicitly switch to the LIBRARY tab before extracting game titles."
            )
        if guidance.strip() not in instructions:
            skill_context["instructions_summary"] = f"{instructions}{guidance}".strip()
        retry_context["skill_context"] = skill_context
        retry_context["planning_failure_feedback"] = (
            "The previous plan was rejected because it only observed the desktop. "
            "Replan with interaction plus explicit extraction."
        )
        return retry_context
    
    def _analyze_failure(
        self,
        goal: AgentGoal,
        state: ExecutionState,
        verification: Dict,
        session_id: str
    ):
        """Analyze why goal wasn't achieved and learn from it."""
        logger.info(f"[AGENT] Analyzing failure for next iteration")
        
        # Detailed failure analysis
        failed_steps = verification.get("failed_steps", [])
        failed_details = verification.get("failed_details", {})
        missing_parts = verification.get("missing_parts", [])
        
        # Log failure analysis with details
        failure_msg = f"Iteration failed: {verification.get('reason', 'Unknown')}"
        if failed_steps:
            failure_msg += f" | Failed steps: {', '.join(failed_steps)}"
        if missing_parts:
            failure_msg += f" | Missing: {', '.join(missing_parts)}"
        
        self.memory.add_message(
            session_id,
            "system",
            failure_msg
        )
        
        # Store detailed failure pattern for learning
        failure_pattern = {
            "goal": goal.goal_text,
            "reason": verification.get("reason"),
            "failed_steps": failed_steps,
            "failed_details": failed_details,
            "missing_parts": missing_parts,
            "plan_complexity": state.plan.complexity,
            "completed_steps": [
                step_id for step_id, result in state.step_results.items()
                if result.status == StepStatus.COMPLETED
            ]
        }
        
        self.memory.learn_pattern("failed_attempts", failure_pattern)
    
    def _update_context_for_retry(
        self,
        context: Optional[Dict],
        state: ExecutionState,
        verification: Dict
    ) -> Dict:
        """Update context with learnings for next iteration."""
        updated = context.copy() if context else {}
        
        # Add previous attempt info with detailed error analysis
        updated["previous_attempt"] = {
            "status": state.status,
            "failed_steps": verification.get("failed_steps", []),
            "failed_details": verification.get("failed_details", {}),
            "missing_parts": verification.get("missing_parts", []),
            "reason": verification.get("reason"),
            "completed_steps": [
                step_id for step_id, result in state.step_results.items()
                if result.status == StepStatus.COMPLETED
            ],
            "step_outputs": {
                step_id: str(result.output)[:500] for step_id, result in state.step_results.items()
                if result.status == StepStatus.COMPLETED
            }
        }
        
        # Add correction guidance
        updated["retry_guidance"] = self._generate_retry_guidance(verification, state)
        
        return updated
    
    def _generate_retry_guidance(self, verification: Dict, state: ExecutionState) -> str:
        """Generate guidance for retry based on failure analysis."""
        guidance = []
        
        # Analyze failure type
        failed_steps = verification.get("failed_steps", [])
        missing_parts = verification.get("missing_parts", [])
        
        if failed_steps:
            guidance.append(f"Fix or replace these failed steps: {', '.join(failed_steps)}")
            
            # Add specific error details
            failed_details = verification.get("failed_details", {})
            for step_id, error in failed_details.items():
                if "parameter" in error.lower():
                    guidance.append(f"Step {step_id}: Check parameter values and types")
                elif "not found" in error.lower() or "unknown" in error.lower():
                    guidance.append(f"Step {step_id}: Verify tool/operation exists")
                elif "timeout" in error.lower() or "network" in error.lower():
                    guidance.append(f"Step {step_id}: Add retry logic or increase timeout")
        
        if missing_parts:
            guidance.append(f"Add steps to complete: {', '.join(missing_parts)}")
        
        if not guidance:
            guidance.append("Review plan structure and step dependencies")
        
        return " | ".join(guidance)
    
    def get_status(self, session_id: str) -> Dict[str, Any]:
        """Get current agent status for session."""
        context = self.memory.get_session(session_id)
        
        if not context:
            return {"status": "no_active_session"}
        
        return {
            "status": "active" if context.active_goal else "idle",
            "active_goal": context.active_goal,
            "message_count": len(context.messages),
            "execution_count": len(context.execution_history)
        }

    def _normalize_tool_result(self, result: Any) -> Dict[str, Any]:
        """Normalize BaseTool ToolResult payloads into plain success/error dicts."""
        if isinstance(result, dict):
            if "success" in result:
                return result
            if "status" in result and "data" in result:
                status_value = str(result.get("status", "")).lower()
                data = result.get("data")
                normalized = dict(data) if isinstance(data, dict) else {"data": data}
                normalized.setdefault("success", status_value == "success")
                if result.get("error_message"):
                    normalized.setdefault("error", result.get("error_message"))
                return normalized
            return {"success": True, **result}

        if hasattr(result, "is_success") and hasattr(result, "data"):
            data = getattr(result, "data", None)
            normalized = dict(data) if isinstance(data, dict) else {"data": data}
            normalized.setdefault("success", bool(result.is_success()))
            error_message = getattr(result, "error_message", None)
            if error_message:
                normalized.setdefault("error", error_message)
            return normalized

        if hasattr(result, "status") and hasattr(result, "data"):
            status = getattr(result, "status", None)
            status_value = getattr(status, "value", status)
            data = getattr(result, "data", None)
            normalized = dict(data) if isinstance(data, dict) else {"data": data}
            normalized.setdefault("success", str(status_value).lower() == "success")
            error_message = getattr(result, "error_message", None)
            if error_message:
                normalized.setdefault("error", error_message)
            return normalized

        return {"success": bool(result), "data": result}

