"""Autonomous Agent - Self-directed goal achievement with planning and execution."""
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from core.task_planner import TaskPlanner, ExecutionPlan
from core.execution_engine import ExecutionEngine, ExecutionState, StepStatus
from core.memory_system import MemorySystem
from core.skills import SkillSelector, build_skill_planning_context

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
    
    def achieve_goal(
        self,
        goal: AgentGoal,
        session_id: str,
        context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Autonomously work toward achieving a goal.
        
        Returns:
            Result dict with success status, iterations, and final state
        """
        logger.info(f"Agent starting goal: {goal.goal_text}")
        
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
        
        while iteration < goal.max_iterations and not success:
            iteration += 1
            logger.info(f"Goal iteration {iteration}/{goal.max_iterations}")
            
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
                execution_id = f"{session_id}_iter{iteration}"
                state = self.executor.execute_plan(plan, execution_id)
                execution_history.append(execution_id)
                final_state = state
                
                # Link execution to session
                self.memory.add_execution(session_id, execution_id)
                
                # Step 3: Verify
                verification = self._verify_results(goal, state, session_id)
                
                if verification["success"]:
                    success = True
                    logger.info(f"Goal achieved in {iteration} iterations")
                    break
                
                # Step 4: Analyze failure and prepare for retry
                if iteration < goal.max_iterations:
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
    
    def _plan_iteration(
        self,
        goal: AgentGoal,
        session_id: str,
        context: Optional[Dict],
        iteration: int
    ) -> Optional[ExecutionPlan]:
        """Plan for current iteration."""
        logger.info(f"Planning iteration {iteration}")
        
        # Get conversation context
        conv_summary = self.memory.get_conversation_summary(session_id)
        
        # Enhance context with memory
        enhanced_context = context or {}
        enhanced_context["conversation_summary"] = conv_summary
        enhanced_context["iteration"] = iteration

        if self.skill_registry:
            selection = self.skill_selector.select_skill(goal.goal_text, self.skill_registry, self.llm_client)
            if selection.matched and selection.skill_name:
                skill = self.skill_registry.get(selection.skill_name)
                if skill:
                    skill_context = build_skill_planning_context(skill)
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
                        "instructions_summary": skill_context.instructions_summary,
                        "preferred_tools": skill_context.preferred_tools,
                        "required_tools": skill_context.required_tools,
                        "verification_mode": skill_context.verification_mode,
                        "output_types": skill_context.output_types,
                        "ui_renderer": skill_context.ui_renderer,
                        "skill_constraints": skill_context.skill_constraints,
                    }

        # Add learned patterns
        similar_patterns = self.memory.get_patterns("successful_goals", limit=3)
        if similar_patterns:
            enhanced_context["similar_successful_approaches"] = similar_patterns
        
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
        logger.info("Verifying execution results")
        
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
                
                # Parse JSON response
                import json
                try:
                    result = json.loads(response) if isinstance(response, str) else response
                    return {
                        "success": result.get("success", False),
                        "reason": result.get("reason", "Unknown"),
                        "details": result.get("details", ""),
                        "missing_parts": result.get("missing_parts", [])
                    }
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
                # Fall back to basic check
                return {
                    "success": len(completed_steps) == len(state.step_results),
                    "reason": "All steps completed" if len(completed_steps) == len(state.step_results) else "Some steps incomplete"
                }
        
        # Default: success if all steps completed
        return {
            "success": len(completed_steps) == len(state.step_results),
            "reason": "All steps completed"
        }
    
    def _build_verification_prompt(
        self,
        goal: AgentGoal,
        state: ExecutionState,
        session_id: str
    ) -> str:
        """Build prompt for LLM to verify goal achievement."""
        # Get step results summary
        results_summary = []
        for step_id, result in state.step_results.items():
            results_summary.append(
                f"- {step_id}: {result.status.value} - Output: {str(result.output)[:200]}"
            )
        
        return f"""Verify if the ENTIRE goal was achieved based on execution results.

GOAL: {goal.goal_text}

SUCCESS CRITERIA:
{chr(10).join(f"- {c}" for c in goal.success_criteria)}

EXECUTION RESULTS:
{chr(10).join(results_summary)}

CRITICAL: Check if ALL parts of the goal were completed:
1. Break down the goal into individual sub-tasks
2. Verify EACH sub-task was completed in the execution results
3. Only respond SUCCESS if EVERY part of the goal is done

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
    
    def _analyze_failure(
        self,
        goal: AgentGoal,
        state: ExecutionState,
        verification: Dict,
        session_id: str
    ):
        """Analyze why goal wasn't achieved and learn from it."""
        logger.info("Analyzing failure for next iteration")
        
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
