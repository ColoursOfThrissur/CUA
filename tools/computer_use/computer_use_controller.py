"""
ComputerUseController - Desktop automation subsystem with an Observe→Act→Evaluate→Adapt loop.

Architecture:
- PlannerAgent: Intent → Plan
- ExecutorAgent: Plan → Execution Trace
- VerifierAgent: Trace → Success/Failure Analysis
- CriticAgent: Failure → Adaptation Strategy
- Controller: Orchestrates the feedback loop

Flow:
1. OBSERVE: Capture current state
2. ACT: Execute plan via ExecutorAgent
3. EVALUATE: Verify results via VerifierAgent
4. ADAPT: If failed, CriticAgent analyzes and PlannerAgent replans
"""
import logging
import time
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Any, Optional

from tools.tool_interface import BaseTool
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel
from tools.computer_use.planner_agent import PlannerAgent
from tools.computer_use.executor_agent import ExecutorAgent
from tools.computer_use.verifier_agent import VerifierAgent
from tools.computer_use.critic_agent import CriticAgent
from tools.computer_use.task_state import infer_task_state
from tools.computer_use.visual_policy import build_visual_policy_plan

logger = logging.getLogger(__name__)

MAX_ADAPT_CYCLES = 3  # Allow up to 3 cycles for multi-step tasks
MAX_PROGRESS_EXTENSION_CYCLES = 3  # Extend up to 3 times if progress is verified


class ComputerUseController(BaseTool):
    """Desktop automation controller with an Observe→Act→Evaluate→Adapt loop."""

    def __init__(self, orchestrator=None):
        self.description = "Desktop automation subsystem with an Observe→Act→Evaluate→Adapt feedback loop. Use for complex interactive workflows, not as the default for every task."
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
        self.orchestrator = orchestrator
        
        # Initialize agents
        if self.services and self.services.llm:
            self.planner = PlannerAgent(llm_client=self.services.llm, orchestrator=orchestrator)
            self.executor = ExecutorAgent(orchestrator=orchestrator)
            self.verifier = VerifierAgent(llm_client=self.services.llm)
            self.critic = CriticAgent(llm_client=self.services.llm)
        else:
            self.planner = None
            self.executor = None
            self.verifier = None
            self.critic = None
        
        # Enable tool collaboration
        self.enable_tool_collaboration = True
        
        # Workflow state
        self.workflow_state = {
            "current_intent": None,
            "cycle_history": [],
            "screen_summary": None,  # Track screen state across cycles
            "screen_analysis": None,
            "completed_steps": [],
            "last_expectation_results": [],
            "last_ui_elements": [],
            "task_state": {},
            "run_image_paths": set(),
        }
        
        super().__init__()

    def register_capabilities(self):
        """Register high-level workflow capabilities."""
        
        self.add_capability(ToolCapability(
            name="automate_task",
            description="Execute task with Observe→Act→Evaluate→Adapt loop. Automatically replans on failure. Can use context from previous tool executions.",
            parameters=[
                Parameter("intent", ParameterType.STRING, "High-level task description", required=True),
                Parameter("max_adapt_cycles", ParameterType.INTEGER, "Max adaptation cycles. Default: 3", required=False),
                Parameter("context", ParameterType.DICT, "Context from previous executions (conversation_history, previous_tool_outputs, session_id)", required=False),
            ],
            returns="dict with success, intent, cycles, final_result",
            safety_level=SafetyLevel.HIGH,
            examples=[
                {"intent": "Open Chrome and navigate to google.com"},
                {"intent": "Take screenshot and analyze what's on screen"},
                {"intent": "Find the Steam library and list visible games", "context": {"previous_tool_outputs": []}}
            ],
            dependencies=[]
        ), self._handle_automate_task)

        self.add_capability(ToolCapability(
            name="get_workflow_state",
            description="Get current workflow state and cycle history.",
            parameters=[],
            returns="dict with current_intent, cycle_history",
            safety_level=SafetyLevel.LOW,
            examples=[{}],
            dependencies=[]
        ), self._handle_get_workflow_state)

        self.add_capability(ToolCapability(
            name="get_failure_insights",
            description="Get failure pattern analysis and trends.",
            parameters=[],
            returns="dict with trends, insights, patterns",
            safety_level=SafetyLevel.LOW,
            examples=[{}],
            dependencies=[]
        ), self._handle_get_failure_insights)

    # ── Main Workflow Handler ─────────────────────────────────────────────

    def _handle_automate_task(self, intent: str, max_adapt_cycles: int = 3, context: Optional[Dict] = None) -> dict:
        """
        Execute task with full Observe→Act→Evaluate→Adapt loop.
        """
        self._sync_agents()

        try:
            context = dict(context or {})
            max_cycles = max(1, min(int(max_adapt_cycles or MAX_ADAPT_CYCLES), MAX_ADAPT_CYCLES))

            self._cleanup_run_artifacts()
            self.workflow_state["current_intent"] = intent
            self.workflow_state["cycle_history"] = []
            self.workflow_state["completed_steps"] = []
            self.workflow_state["last_expectation_results"] = []
            self.workflow_state["task_state"] = {}

            observed_context = self._observe()
            observed_context.update(context)

            orchestrated_result = self._try_main_orchestrator_execution(intent, observed_context)
            if orchestrated_result is not None:
                return orchestrated_result

            if not self._agents_available():
                return {"success": False, "error": "Agents not available and main orchestrator execution unavailable"}
            cycle_context = observed_context
            progress_extensions = 0

            for cycle_num in range(1, max_cycles + 1):
                cycle_result = self._run_cycle(intent, cycle_context, cycle_num)
                self.workflow_state["cycle_history"].append(cycle_result)

                if cycle_result.get("success"):
                    self._record_trajectory_success(intent, cycle_result)
                    return {
                        "success": True,
                        "intent": intent,
                        "cycles": cycle_num,
                        "final_result": cycle_result,
                        "cycle_history": self.workflow_state["cycle_history"],
                    }

                if cycle_result.get("continue_from_progress"):
                    cycle_context = self._observe()
                    cycle_context.update(context)
                    cycle_context["force_vision"] = True
                    if progress_extensions < MAX_PROGRESS_EXTENSION_CYCLES:
                        progress_extensions += 1
                        max_cycles += 1
                    continue

                if cycle_num < max_cycles:
                    cycle_context = self._adapt(cycle_result, cycle_context)

            self._record_trajectory_failure(intent)
            return {
                "success": False,
                "intent": intent,
                "cycles": len(self.workflow_state["cycle_history"]),
                "final_result": self.workflow_state["cycle_history"][-1] if self.workflow_state["cycle_history"] else None,
                "cycle_history": self.workflow_state["cycle_history"],
                "error": "Task did not complete within adaptation budget",
            }
        except Exception as e:
            logger.error(f"Automate task failed: {e}")
            return {"success": False, "error": str(e)}

    def _try_main_orchestrator_execution(self, intent: str, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Use the shared CUA planner and execution engine when available."""
        if not self.orchestrator:
            return None

        task_planner = getattr(self.orchestrator, "main_planner", None)
        execution_engine = getattr(self.orchestrator, "execution_engine", None)
        if not task_planner or not execution_engine:
            return None

        try:
            planning_context = dict(context)
            skill_context = dict(planning_context.get("skill_context") or {})
            preferred_tools = list(skill_context.get("preferred_tools") or [])
            if preferred_tools:
                preferred_tools = [tool for tool in preferred_tools if tool != "ComputerUseController"]
                for tool_name in ("SystemControlTool", "InputAutomationTool", "ScreenPerceptionTool"):
                    if tool_name not in preferred_tools:
                        preferred_tools.append(tool_name)
                skill_context["preferred_tools"] = preferred_tools
                planning_context["skill_context"] = skill_context
            elif skill_context:
                planning_context["skill_context"] = skill_context
            excluded_tools = list(planning_context.get("excluded_tools") or [])
            if "ComputerUseController" not in excluded_tools:
                excluded_tools.append("ComputerUseController")
            planning_context["excluded_tools"] = excluded_tools
            planning_context["computer_use_requested"] = True

            execution_plan = task_planner.plan_task(intent, planning_context)
            if not getattr(execution_plan, "steps", None):
                return None

            if any(getattr(step, "tool_name", "") == self.__class__.__name__ for step in execution_plan.steps):
                logger.info("Main planner produced recursive ComputerUseController plan; using internal fallback loop")
                return None

            execution_id = f"computer_use_{int(time.time())}"
            state = execution_engine.execute_plan(
                execution_plan,
                execution_id=execution_id,
                pause_on_failure=False,
                skill_context=None,
            )

            return {
                "success": state.status == "completed" and not state.error,
                "intent": intent,
                "mode": "main_orchestrator",
                "execution_id": execution_id,
                "plan": asdict(execution_plan),
                "execution": self._serialize_execution_state(state),
                "cycle_history": [],
                "error": state.error,
            }
        except Exception as e:
            logger.warning(f"Main orchestrator execution failed for computer-use task: {e}")
            return None

    def _serialize_execution_state(self, state: Any) -> Dict[str, Any]:
        """Make ExecutionState safe to return from the tool capability."""
        step_results = {}
        for step_id, step_result in getattr(state, "step_results", {}).items():
            if hasattr(step_result, "to_serializable"):
                step_results[step_id] = step_result.to_serializable()
            else:
                step_results[step_id] = {
                    "status": str(getattr(step_result, "status", "")),
                    "output": getattr(step_result, "output", None),
                    "error": getattr(step_result, "error", None),
                }

        end_time = getattr(state, "end_time", None) or time.time()
        start_time = getattr(state, "start_time", end_time)
        return {
            "status": getattr(state, "status", "unknown"),
            "error": getattr(state, "error", None),
            "current_step": getattr(state, "current_step", None),
            "duration_seconds": end_time - start_time,
            "step_results": step_results,
        }

    def _clean_for_llm(self, data: Any) -> Any:
        """Deep clean massive base64 fields so they don't break main planner context."""
        if isinstance(data, dict):
            return {
                k: "<base64_removed>" if k == "thumbnail" else self._clean_for_llm(v)
                for k, v in data.items()
            }
        elif isinstance(data, list):
            return [self._clean_for_llm(item) for item in data]
        return data

    def _run_cycle(self, intent: str, context: Dict, cycle_num: int) -> Dict:
        """
        Run single Observe→Act→Evaluate→Adapt cycle.
        
        Returns cycle result with all agent outputs.
        """
        cycle_start = time.time()
        
        # 1. OBSERVE (already done, context passed in)
        logger.info("1. OBSERVE: Current state captured")
        
        # 2. PLAN - Vision model switching: Try OCR first for simple tasks
        logger.info("2. PLAN: Vision model switching")
        
        # VISION MODEL SWITCHING: Detect task complexity
        task_complexity = self._assess_task_complexity(intent, context)
        
        if task_complexity == "simple":
            # Simple task: Try OCR-based direct action (no LLM)
            logger.info("2a. SIMPLE TASK: Attempting OCR-based direct action")
            ocr_result = self._try_ocr_direct_action(intent, context)
            
            if ocr_result and ocr_result.get("success"):
                logger.info("2a. OCR: Direct action succeeded, skipping LLM planning")
                # Wrap OCR result as execution trace
                execution_result = {
                    "success": True,
                    "trace": [{
                        "step": 1,
                        "tool": "OCRClicker",
                        "operation": "find_and_click",
                        "params": {"target": ocr_result.get("target")},
                        "result": ocr_result,
                        "success": True,
                        "before_state": {},
                        "after_state": {},
                    }]
                }
                
                # Brief stabilization
                time.sleep(0.5)
                
                # Verify with simple check
                verification_result = {"verified": True, "confidence": 0.9}
                task_complete = self._is_task_complete(intent, execution_result, verification_result)
                
                cycle_time = time.time() - cycle_start
                
                if task_complete:
                    return {
                        "success": True,
                        "cycle": cycle_num,
                        "plan": [{"tool": "OCRClicker", "operation": "find_and_click"}],
                        "executed_chunk": [{"tool": "OCRClicker", "operation": "find_and_click"}],
                        "execution": execution_result,
                        "verification": verification_result,
                        "cycle_time": cycle_time,
                        "method": "ocr_direct",
                    }
        
        # Fallback to vision-based LLM planning
        logger.info(f"2b. {task_complexity.upper()} TASK: Using LLM planning with vision")
        
        # Pass vision data from context to prevent duplicate calls
        planning_context = dict(context)
        if self.workflow_state.get("screen_summary"):
            planning_context["screen_summary"] = self.workflow_state["screen_summary"]
        if self.workflow_state.get("screen_analysis"):
            planning_context["screen_analysis"] = self.workflow_state["screen_analysis"]
        
        policy_plan = build_visual_policy_plan(intent, planning_context)
        if policy_plan:
            logger.info(f"2c. POLICY: Using grounded visual policy: {[step['operation'] for step in policy_plan]}")
            plan_result = {
                "success": True,
                "plan": policy_plan,
                "intent": intent,
                "strategy": "visual_policy",
            }
        else:
            plan_result = self.planner.generate_plan(intent, planning_context)
        
        # Update workflow state with latest vision summary
        if self.planner.vision_cache.get("summary"):
            self.workflow_state["screen_summary"] = self.planner.vision_cache["summary"]
        
        if not plan_result.get("success"):
            return {
                "success": False,
                "cycle": cycle_num,
                "phase": "PLAN",
                "error": plan_result.get("error", "Planning failed"),
            }
        
        plan = plan_result["plan"]
        plan_confidence = plan_result.get("confidence", 0.5)
        logger.info(f"Plan generated: {len(plan)} steps, confidence={plan_confidence:.2f}")
        
        # Pass confidence to context for chunking
        context["plan_confidence"] = plan_confidence
        execution_chunk = self._select_execution_chunk(plan, context)
        logger.info(f"Chunk selected: {len(execution_chunk)}/{len(plan)} step(s)")
        
        # 3. ACT
        logger.info("3. ACT: Executing plan")
        execution_result = self.executor.execute_plan(execution_chunk, capture_state=True)
        
        # Brief stabilization delay after execution
        time.sleep(0.5)
        
        # 4. EVALUATE
        logger.info("4. EVALUATE: Verifying execution")
        verification_result = self.verifier.verify_execution(execution_result)
        task_complete = self._is_task_complete(intent, execution_result, verification_result)

        # Check if successful
        if execution_result.get("success") and verification_result.get("verified") and task_complete:
            cycle_time = time.time() - cycle_start
            remaining_steps = plan[len(execution_chunk):]
            self.workflow_state["completed_steps"].extend(execution_chunk)
            self.workflow_state["last_expectation_results"] = verification_result.get("expectation_results", [])
            self._update_state_from_execution(intent, execution_result)

            if remaining_steps:
                return {
                    "success": False,
                    "continue_from_progress": True,
                    "cycle": cycle_num,
                    "plan": plan,
                    "executed_chunk": execution_chunk,
                    "remaining_steps": remaining_steps,
                    "execution": execution_result,
                    "verification": verification_result,
                    "cycle_time": cycle_time,
                }

            return {
                "success": True,
                "cycle": cycle_num,
                "plan": plan,
                "executed_chunk": execution_chunk,
                "execution": execution_result,
                "verification": verification_result,
                "cycle_time": cycle_time,
            }

        if execution_result.get("success") and verification_result.get("verified") and not task_complete:
            cycle_time = time.time() - cycle_start
            made_progress = self._made_actionable_progress(execution_result)
            if made_progress:
                self.workflow_state["completed_steps"].extend(execution_chunk)
                self.workflow_state["last_expectation_results"] = verification_result.get("expectation_results", [])
                self._update_state_from_execution(intent, execution_result)
            return {
                "success": False,
                "continue_from_progress": made_progress,
                "cycle": cycle_num,
                "plan": plan,
                "executed_chunk": execution_chunk,
                "remaining_steps": plan[len(execution_chunk):],
                "execution": execution_result,
                "verification": verification_result,
                "cycle_time": cycle_time,
            }
        
        # 5. ADAPT (failure case)
        logger.info("5. ADAPT: Analyzing failure and generating adaptation")
        adaptation = self.critic.analyze_and_adapt(
            original_plan=plan,
            execution_result=execution_result,
            verification_result=verification_result,
            context=context
        )
        
        cycle_time = time.time() - cycle_start
        
        return {
            "success": False,
            "cycle": cycle_num,
            "plan": plan,
            "executed_chunk": execution_chunk,
            "execution": execution_result,
            "verification": verification_result,
            "adaptation": adaptation,
            "cycle_time": cycle_time,
        }

    def _observe(self) -> Dict:
        """
        OBSERVE phase: Capture current environment state.
        
        Returns context dict with:
        - screen_summary (from workflow state for memory)
        - open_windows
        - active_window
        - screen_resolution
        - available_tools (for collaboration)
        """
        context = {}
        
        try:
            # Add available tools for collaboration
            if self.enable_tool_collaboration and self.orchestrator and hasattr(self.orchestrator, '_registry'):
                registry = self.orchestrator._registry
                if registry:
                    available_tools = []
                    for tool in registry.tools:
                        tool_name = tool.__class__.__name__
                        # Skip computer use tools to avoid recursion
                        if "Computer" not in tool_name and "Screen" not in tool_name and "Input" not in tool_name:
                            caps = tool.get_capabilities() if hasattr(tool, 'get_capabilities') else {}
                            if caps:
                                available_tools.append({
                                    "name": tool_name,
                                    "operations": list(caps.keys())[:5]  # Limit to 5 ops per tool
                                })
                    if available_tools:
                        context["available_tools"] = available_tools[:10]  # Limit to 10 tools
            
            # Get screen info
            screen_info = self.services.call_tool("ScreenPerceptionTool", "get_screen_info")
            if screen_info.get("success"):
                context["screen_resolution"] = {
                    "width": screen_info.get("width"),
                    "height": screen_info.get("height"),
                }

            # Get open windows
            windows_result = self.services.call_tool("SystemControlTool", "list_windows")
            if windows_result.get("success"):
                windows = windows_result.get("windows", [])
                context["open_windows"] = [w["title"] for w in windows[:10]]  # Top 10
                
                # Find active window
                active = next((w for w in windows if w.get("is_active")), None)
                if active:
                    context["active_window"] = active["title"]

            # Pass previous screen summary for memory (PlannerAgent will update)
            if self.workflow_state.get("screen_summary"):
                context["screen_summary"] = self.workflow_state["screen_summary"]
            if self.workflow_state.get("screen_analysis"):
                context["screen_analysis"] = self.workflow_state["screen_analysis"]
            if self.workflow_state.get("last_ui_elements"):
                context["ui_elements"] = self.workflow_state["last_ui_elements"][-12:]

            # Only do vision calls if forced or no recent data
            # This prevents request backlog from rapid sequential calls
            should_do_vision = context.get("force_vision", False) or not self.workflow_state.get("last_ui_elements")
            
            if should_do_vision:
                target_app = infer_task_state(self.workflow_state.get("current_intent", ""), context).target_app
                
                # OPTIMIZED: Use comprehensive_state for single batched call
                # Replaces 3 separate calls (infer_visual_state + detect_ui_elements + locate_target)
                comprehensive_result = self.services.call_tool(
                    "ScreenPerceptionTool",
                    "get_comprehensive_state",
                    target_app=target_app,
                )
                
                if comprehensive_result.get("success"):
                    # Extract all data from single call
                    context["visual_state"] = comprehensive_result.get("visual_state", {})
                    context["ui_elements"] = comprehensive_result.get("elements", [])[:16]
                    
                    # Store in workflow state
                    self.workflow_state["last_ui_elements"] = context["ui_elements"]
                    
                    # Store screen_analysis for planner reuse
                    visual_state = comprehensive_result.get("visual_state", {})
                    notes = visual_state.get("notes", "")
                    if notes:
                        self.workflow_state["screen_analysis"] = notes
                        context["screen_analysis"] = notes
                    
                    self._track_image_path(comprehensive_result.get("image_path"))
                    
                    logger.info(f"[OPTIMIZED] Single comprehensive_state call returned visual_state + {len(context['ui_elements'])} elements")
            else:
                # Reuse cached data
                if self.workflow_state.get("last_ui_elements"):
                    context["ui_elements"] = self.workflow_state["last_ui_elements"]

            if self.workflow_state.get("completed_steps"):
                context["completed_steps"] = [
                    {
                        "tool": step.get("tool"),
                        "operation": step.get("operation"),
                        "parameters": step.get("parameters") or step.get("params", {}),
                    }
                    for step in self.workflow_state["completed_steps"][-5:]
                ]
            if self.workflow_state.get("last_expectation_results"):
                context["last_expectation_results"] = self.workflow_state["last_expectation_results"][-5:]
            task_state = infer_task_state(self.workflow_state.get("current_intent", ""), context)
            self.workflow_state["task_state"] = task_state.to_dict()
            context["task_state"] = self.workflow_state["task_state"]

        except Exception as e:
            logger.warning(f"Observation incomplete: {e}")

        return context

    def _adapt(self, cycle_result: Dict, old_context: Dict) -> Dict:
        """
        ADAPT phase: Update context based on failure analysis.
        
        Returns updated context for next cycle.
        """
        # Re-observe environment (state may have changed)
        new_context = self._observe()
        
        # Force vision on next cycle (screen changed after execution)
        new_context["force_vision"] = True
        
        # Add adaptation insights to context
        adaptation = cycle_result.get("adaptation", {})
        
        # Extract specific error details from execution
        execution = cycle_result.get("execution", {})
        error_msg = execution.get("error", "")
        
        # Parse parameter errors (e.g., "Missing required parameters for Tool.op: param_name")
        missing_param = None
        if "Missing required parameters" in error_msg:
            import re
            match = re.search(r'Missing required parameters for [^:]+: (\w+)', error_msg)
            if match:
                missing_param = match.group(1)
        
        new_context["previous_failure"] = {
            "root_cause": adaptation.get("root_cause") or error_msg[:200],
            "strategy": adaptation.get("adaptation_strategy"),
            "suggestions": adaptation.get("suggested_changes", []),
            "missing_parameter": missing_param,  # Explicit parameter name
        }
        
        # If critic suggests replanning, pass failure info to planner
        if adaptation.get("should_replan"):
            new_context["replan_needed"] = True
            new_context["failure_info"] = cycle_result.get("verification", {}).get("failure_analysis", {})
        
        return new_context

    def _try_ocr_direct_action(self, intent: str, context: Dict) -> Optional[Dict]:
        """
        Try OCR-based direct action for simple click tasks.
        
        Detects patterns like:
        - "Open [app]"
        - "Click [button]"
        - "Launch [program]"
        
        Returns OCR click result or None if not applicable.
        """
        try:
            from tools.computer_use.ocr_clicker import OCRClicker
            
            intent_lower = intent.lower()
            
            # Pattern detection
            click_patterns = [
                (r"open\s+(.+)", "open"),
                (r"launch\s+(.+)", "launch"),
                (r"click\s+(.+)", "click"),
                (r"start\s+(.+)", "start"),
            ]
            
            import re
            target = None
            action = None
            
            for pattern, action_type in click_patterns:
                match = re.search(pattern, intent_lower)
                if match:
                    target = match.group(1).strip()
                    action = action_type
                    break
            
            if not target:
                logger.debug("OCR: No simple click pattern detected")
                return None
            
            # Skip if target is too complex (multi-word with "and")
            if " and " in target or len(target.split()) > 3:
                logger.info(f"OCR: Target too complex: '{target}', falling back to LLM")
                return None
            
            logger.info(f"OCR: Attempting direct action '{action}' on target '{target}'")
            
            clicker = OCRClicker(orchestrator=self.orchestrator)
            result = clicker.find_and_click(target, fuzzy=True)
            
            if result.get("success"):
                logger.info(f"OCR: Successfully clicked '{result.get('found_text')}' at {result.get('clicked_at')}")
                result["target"] = target
                return result
            else:
                logger.info(f"OCR: Failed - {result.get('error')}, falling back to LLM")
                return None
                
        except ImportError as e:
            logger.warning(f"OCR libraries not available: {e}. Install pytesseract or easyocr.")
            return None
        except Exception as e:
            logger.warning(f"OCR direct action failed: {e}, falling back to LLM")
            return None

    def _select_execution_chunk(self, plan: List[Dict], context: Dict) -> List[Dict]:
        """
        Execute only a short-horizon chunk of the plan.

        CONFIDENCE-BASED CHUNKING:
        - High confidence (≥0.8): Execute up to 3 steps
        - Medium confidence (0.5-0.8): Execute up to 2 steps  
        - Low confidence (<0.5): Execute 1 step only
        
        Interactive operations always execute 1 step for frequent re-observation.
        """
        if not plan:
            return []
        if len(plan) == 1:
            return plan

        first = plan[0]
        tool = first.get("tool", "")
        operation = first.get("operation", "")
        interactive_tools = {"InputAutomationTool", "SystemControlTool", "ScreenPerceptionTool"}
        interactive_ops = {
            "smart_click", "click", "type_text", "press_key", "hotkey",
            "launch_application", "focus_window", "smart_focus_window",
        }

        # Interactive operations: always 1 step for tight feedback loop
        if tool in interactive_tools or operation in interactive_ops:
            return [first]
        
        # Non-interactive: use confidence-based chunking
        plan_confidence = context.get("plan_confidence", 0.5)
        
        if plan_confidence >= 0.8:
            chunk_size = 3
        elif plan_confidence >= 0.5:
            chunk_size = 2
        else:
            chunk_size = 1
        
        logger.info(f"Confidence-based chunking: confidence={plan_confidence:.2f}, chunk_size={chunk_size}")
        return plan[:chunk_size]

    def _carry_forward_progress(self, cycle_result: Dict, old_context: Dict) -> Dict:
        """Carry successful chunk progress into the next planning round."""
        new_context = self._observe()
        executed_chunk = cycle_result.get("executed_chunk", [])
        remaining_steps = cycle_result.get("remaining_steps", [])
        verification = cycle_result.get("verification", {})
        execution = cycle_result.get("execution", {})

        trace = execution.get("trace", [])
        if trace:
            last_result = trace[-1].get("result", {})
            if isinstance(last_result, dict) and isinstance(last_result.get("elements"), list):
                self.workflow_state["last_ui_elements"] = last_result.get("elements", [])
            if isinstance(last_result, dict) and isinstance(last_result.get("analysis"), str):
                self.workflow_state["screen_analysis"] = last_result.get("analysis")
            if isinstance(last_result, dict):
                self._track_image_path(last_result.get("image_path"))

        new_context["progress_made"] = True
        new_context["completed_chunk"] = [
            {
                "tool": step.get("tool"),
                "operation": step.get("operation"),
                "parameters": step.get("parameters") or step.get("params", {}),
            }
            for step in executed_chunk
        ]
        new_context["remaining_steps_hint"] = [
            {
                "tool": step.get("tool"),
                "operation": step.get("operation"),
                "parameters": step.get("parameters") or step.get("params", {}),
            }
            for step in remaining_steps[:3]
        ]
        new_context["last_verification"] = {
            "verified": verification.get("verified"),
            "expectation_results": verification.get("expectation_results", []),
            "state_changes": verification.get("state_changes", []),
        }
        return new_context

    def _update_state_from_execution(self, intent: str, execution_result: Dict) -> None:
        """Fold useful artifacts from execution back into workflow state."""
        trace = execution_result.get("trace", [])
        for step in trace:
            result = step.get("result", {}) or {}
            if not isinstance(result, dict):
                continue
            if isinstance(result.get("elements"), list):
                self.workflow_state["last_ui_elements"] = result.get("elements", [])
            if isinstance(result.get("analysis"), str):
                self.workflow_state["screen_analysis"] = result.get("analysis")
            self._track_image_path(result.get("image_path"))
            self._track_image_path(step.get("before_state", {}).get("screenshot_path"))
            self._track_image_path(step.get("after_state", {}).get("screenshot_path"))
        observed = self._observe()
        if observed.get("task_state"):
            self.workflow_state["task_state"] = observed["task_state"]

    def _is_task_complete(self, intent: str, execution_result: Dict, verification_result: Dict) -> bool:
        """Check if task is complete using LLM evaluation."""
        if not execution_result.get("success") or not verification_result.get("verified"):
            return False
        try:
            completed_steps = self.workflow_state.get("completed_steps", [])
            trace = execution_result.get("trace", [])
            steps_summary = []
            for step in completed_steps:
                tool = step.get("tool", "")
                operation = step.get("operation", "")
                params = step.get("parameters", {})
                steps_summary.append(f"- {tool}.{operation}({', '.join(f'{k}={v}' for k, v in list(params.items())[:2])})")
            for step in trace:
                tool = step.get("tool", "")
                operation = step.get("operation", "")
                result = step.get("result", {})
                success = result.get("success", False) if isinstance(result, dict) else False
                steps_summary.append(f"- {tool}.{operation}: {'✓' if success else '✗'}")
            prompt = f"""RETURN ONLY VALID JSON. NO TEXT. NO EXPLANATION.

Evaluate if this task is fully complete.

ORIGINAL GOAL: {intent}

COMPLETED STEPS:
{chr(10).join(steps_summary) if steps_summary else '(none)'}

VERIFICATION: {verification_result.get('summary', 'Steps executed successfully')}

Is the ORIGINAL GOAL fully achieved?

CRITICAL RULES:
- Tasks with "and" require BOTH parts completed (e.g., "open X and do Y" needs X opened AND Y done)
- "get list", "show list", "list games" requires actual data extraction, not just opening the app
- "find" or "locate" requires identifying the target, not just launching
- Opening an app is NOT the same as extracting data from it

Return this JSON structure:
{{"complete": true, "reason": "All parts of the goal achieved"}}

RULES:
- Return ONLY the JSON object
- complete: true ONLY if ENTIRE goal is done (all parts after "and", all data extracted)
- complete: false if only partial progress made
- reason: brief explanation of what's done vs what's missing

JSON ONLY. START NOW:
"""
            from shared.config.model_manager import get_model_manager
            raw_client = getattr(self.services.llm, '_client', self.services.llm)
            model_manager = get_model_manager(raw_client)
            model_manager.switch_to("planning")
            response = self.services.llm.generate(prompt=prompt, temperature=0.1, max_tokens=150, format="json")
            model_manager.switch_to("chat")
            if response:
                response = response.strip()
                if "```json" in response:
                    response = response[response.find("```json") + 7:response.rfind("```")].strip()
                elif "```" in response:
                    response = response[response.find("```") + 3:response.rfind("```")].strip()
                import json
                try:
                    result = json.loads(response)
                    is_complete = result.get("complete", False)
                    reason = result.get("reason", "")
                    logger.info(f"Task completion check: {is_complete} - {reason}")
                    return is_complete
                except json.JSONDecodeError as decode_err:
                    logger.warning(f"Task completion LLM returned invalid JSON: {decode_err} - raw: {response}")
                    return False
        except Exception as e:
            logger.warning(f"LLM completion check failed: {e}")
            try:
                from shared.config.model_manager import get_model_manager
                raw_client = getattr(self.services.llm, '_client', self.services.llm)
                get_model_manager(raw_client).switch_to("chat")
            except Exception:
                pass
        return len(self.workflow_state.get("completed_steps", [])) >= 2

    def _made_actionable_progress(self, execution_result: Dict) -> bool:
        """Only perception that yields actionable evidence should count as progress."""
        trace = execution_result.get("trace", []) or []
        if not trace:
            return False

        last = trace[-1]
        tool = str(last.get("tool") or "")
        operation = str(last.get("operation") or "")
        result = last.get("result", {}) or {}
        if not isinstance(result, dict) or not result.get("success"):
            return False

        if tool == "ScreenPerceptionTool" and operation == "detect_ui_elements":
            return bool(result.get("elements"))
        if tool == "ScreenPerceptionTool" and operation == "infer_visual_state":
            visual_state = result.get("visual_state", {}) or {}
            return bool(
                visual_state.get("visible_targets")
                or visual_state.get("target_app_visible")
                or (visual_state.get("current_view") not in {"", "unknown"})
            )
        if tool == "ScreenPerceptionTool" and operation == "analyze_screen":
            return bool(str(result.get("analysis", "")).strip())
        return True

    # ── Helper Handlers ────────────────────────────────────────────────────

    def _track_image_path(self, image_path: Optional[str]) -> None:
        if not image_path:
            return
        try:
            path = Path(image_path)
        except Exception:
            return
        if path.parent.name.lower() != "output":
            return
        if not (path.name.startswith("screen_") or path.name.startswith("region_")):
            return
        self.workflow_state.setdefault("run_image_paths", set()).add(str(path))

    def _cleanup_run_artifacts(self) -> None:
        for image_path in list(self.workflow_state.get("run_image_paths", set())):
            try:
                path = Path(image_path)
                if path.exists() and path.parent.name.lower() == "output":
                    path.unlink(missing_ok=True)
            except Exception as e:
                logger.debug(f"Failed to cleanup capture artifact {image_path}: {e}")
        self.workflow_state["run_image_paths"] = set()
    
    def _record_trajectory_success(self, intent: str, cycle_result: Dict) -> None:
        """Record successful trajectory to memory for future reuse."""
        try:
            from infrastructure.persistence.sqlite.cua_database import get_conn
            from datetime import datetime
            import json
            
            # Extract plan from cycle result
            plan = cycle_result.get("plan", [])
            if not plan:
                return
            
            # Normalize intent to pattern
            pattern = self._normalize_intent_pattern(intent)
            if not pattern:
                return
            
            # Serialize plan
            plan_json = json.dumps(plan)
            
            # Calculate execution time
            execution_time_ms = cycle_result.get("cycle_time", 0) * 1000
            
            now = datetime.now().isoformat()
            
            with get_conn() as conn:
                # Check if pattern exists
                existing = conn.execute(
                    "SELECT id, success_count, failure_count, avg_execution_time_ms FROM trajectory_memory WHERE intent_pattern = ?",
                    (pattern,)
                ).fetchone()
                
                if existing:
                    # Update existing
                    row_id, success_count, failure_count, avg_time = existing
                    new_success = success_count + 1
                    total = new_success + failure_count
                    new_avg_time = ((avg_time * (total - 1)) + execution_time_ms) / total
                    
                    conn.execute(
                        """UPDATE trajectory_memory 
                           SET plan_json = ?, success_count = ?, avg_execution_time_ms = ?, last_used = ?
                           WHERE id = ?""",
                        (plan_json, new_success, new_avg_time, now, row_id)
                    )
                else:
                    # Insert new
                    conn.execute(
                        """INSERT INTO trajectory_memory 
                           (intent_pattern, plan_json, success_count, failure_count, avg_execution_time_ms, last_used, created_at)
                           VALUES (?, ?, 1, 0, ?, ?, ?)""",
                        (pattern, plan_json, execution_time_ms, now, now)
                    )
                
                logger.info(f"Trajectory memory RECORD: pattern='{pattern}', plan_steps={len(plan)}")
            
        except Exception as e:
            logger.warning(f"Trajectory memory record failed: {e}")
    
    def _record_trajectory_failure(self, intent: str) -> None:
        """Record trajectory failure to adjust success rates."""
        try:
            from infrastructure.persistence.sqlite.cua_database import get_conn
            from datetime import datetime
            
            pattern = self._normalize_intent_pattern(intent)
            if not pattern:
                return
            
            now = datetime.now().isoformat()
            
            with get_conn() as conn:
                # Only update if pattern exists
                conn.execute(
                    "UPDATE trajectory_memory SET failure_count = failure_count + 1, last_used = ? WHERE intent_pattern = ?",
                    (now, pattern)
                )
            
        except Exception as e:
            logger.warning(f"Trajectory failure record failed: {e}")
    
    def _normalize_intent_pattern(self, intent: str) -> str:
        """Normalize intent to pattern (same logic as PlannerAgent)."""
        intent_lower = intent.lower().strip()
        
        if any(word in intent_lower for word in ["open", "launch", "start"]):
            for app in ["chrome", "notepad", "steam", "vscode", "firefox", "excel", "word"]:
                if app in intent_lower:
                    return f"open_{app}"
            return "open_app"
        
        if "click" in intent_lower:
            return "click_element"
        
        if "type" in intent_lower or "write" in intent_lower:
            return "type_text"
        
        if "screenshot" in intent_lower or "capture" in intent_lower:
            return "capture_screen"
        
        if "find" in intent_lower or "locate" in intent_lower:
            return "find_element"
        
        words = intent_lower.split()[:2]
        return "_".join(words) if words else "unknown"
    
    def _assess_task_complexity(self, intent: str, context: Dict) -> str:
        """Assess task complexity for vision model switching.
        
        Returns:
        - "simple": Single-action tasks (click, open) → Use OCR
        - "medium": Multi-step but straightforward → Use cached elements
        - "complex": Requires deep analysis → Use qwen3.5 vision
        """
        intent_lower = intent.lower().strip()
        
        # Simple: Single action verbs
        simple_patterns = [
            r"^(open|launch|start|click|close)\s+\w+$",  # "open chrome", "click start"
            r"^(find|locate)\s+\w+$",  # "find notepad"
        ]
        
        import re
        for pattern in simple_patterns:
            if re.match(pattern, intent_lower):
                return "simple"
        
        # Complex: Multi-step or analysis tasks
        complex_keywords = [
            "analyze", "compare", "find all", "list all", "show me",
            "what", "how many", "which", "where",
        ]
        
        if any(keyword in intent_lower for keyword in complex_keywords):
            return "complex"
        
        # Complex: Multi-step with "and"
        if " and " in intent_lower:
            return "complex"
        
        # Medium: Everything else
        return "medium"

    def _handle_get_workflow_state(self, **kwargs) -> dict:
        """Get current workflow state."""
        return {
            "success": True,
            "current_intent": self.workflow_state.get("current_intent"),
            "cycle_count": len(self.workflow_state.get("cycle_history", [])),
            "cycle_history": self.workflow_state.get("cycle_history", []),
        }

    def _handle_get_failure_insights(self, **kwargs) -> dict:
        """Get failure pattern analysis."""
        if not self.critic:
            return self._error_response("CRITIC_NOT_AVAILABLE", "Critic agent not initialized")

        try:
            trends = self.critic.analyze_failure_trends()
            patterns = self.critic.get_failure_patterns(limit=20)

            return {
                "success": True,
                "trends": trends.get("trends", {}),
                "insights": trends.get("insights", []),
                "total_failures": trends.get("total_failures", 0),
                "recent_patterns": patterns,
            }

        except Exception as e:
            logger.error(f"Failure insights failed: {e}")
            return self._error_response("INSIGHTS_FAILED", str(e))

    # ── Utility Methods ────────────────────────────────────────────────────

    def _agents_available(self) -> bool:
        """Check if all agents are initialized."""
        return all([self.planner, self.executor, self.verifier, self.critic])

    def _sync_agents(self) -> None:
        """Refresh agent instances if services/orchestrator were rebound during bootstrap."""
        if not self.orchestrator:
            return
        self.services = self.orchestrator.get_services(self.__class__.__name__)
        if not self.services or not self.services.llm:
            return

        current_llm = self.services.llm
        planner_needs_refresh = self.planner is None or getattr(self.planner, "llm", None) is not current_llm
        verifier_needs_refresh = self.verifier is None or getattr(self.verifier, "llm", None) is not current_llm
        critic_needs_refresh = self.critic is None or getattr(self.critic, "llm", None) is not current_llm
        executor_needs_refresh = self.executor is None or getattr(self.executor, "orchestrator", None) is not self.orchestrator

        if planner_needs_refresh:
            self.planner = PlannerAgent(llm_client=current_llm, orchestrator=self.orchestrator)
        if executor_needs_refresh:
            self.executor = ExecutorAgent(orchestrator=self.orchestrator)
        if verifier_needs_refresh:
            self.verifier = VerifierAgent(llm_client=current_llm)
        if critic_needs_refresh:
            self.critic = CriticAgent(llm_client=current_llm)

    def _error_response(self, error_type: str, message: str, **extra) -> dict:
        """Structured error response."""
        return {
            "success": False,
            "error_type": error_type,
            "message": message,
            **extra
        }

    def execute(self, operation: str, **kwargs):
        """Execute capability by name."""
        return self.execute_capability(operation, **kwargs)

    def execute_task(self, intent: str, context: Optional[Dict] = None):
        """
        Execute a task using the feedback loop.
        
        Args:
            intent: User intent for the task.
            context: Additional context for the task.
        
        Returns:
            Execution result.
        """
        return self._handle_automate_task(intent=intent, context=context)
