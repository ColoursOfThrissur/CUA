"""
Evolution Processor - Processes the evolution queue.
"""
import asyncio
from pathlib import Path
from typing import Dict, List, Optional
from application.use_cases.tool_lifecycle.tool_evolution_flow import ToolEvolutionOrchestrator
from application.use_cases.evolution.evolution_queue import EvolutionQueue, QueuedEvolution
from infrastructure.testing.llm_test_orchestrator import LLMTestOrchestrator
from infrastructure.persistence.sqlite.logging import SQLiteLogger
from shared.utils.correlation_context import CorrelationContext
from shared.utils.trace_bridge import broadcast_trace_sync
from domain.value_objects.execution_context import SkillExecutionContext
from infrastructure.validation.ast.architecture_validator import infer_skill_contract_for_tool
from application.services.skill_registry import SkillRegistry

class EvolutionProcessor:
    def __init__(self, logger: SQLiteLogger, queue: EvolutionQueue, config: Dict, llm_client, test_orchestrator: LLMTestOrchestrator, evolution_flow: ToolEvolutionOrchestrator, quality_analyzer):
        self.logger = logger
        self.queue = queue
        self.config = config
        self.llm_client = llm_client
        self.test_orchestrator = test_orchestrator
        self.evolution_flow = evolution_flow
        self.quality_analyzer = quality_analyzer
        self.running = False
        self.tool_creation_flow = None

    async def start(self):
        self.running = True
        self.logger.info("Evolution processor started")
        asyncio.create_task(self._process_loop())

    async def stop(self):
        self.running = False
        self.logger.info("Evolution processor stopped")

    async def _process_loop(self):
        """Process queued evolutions"""
        while self.running:
            try:
                # Get next evolution from queue
                evolution = self.queue.get_next()
                if not evolution:
                    await asyncio.sleep(10)
                    continue
                    
                # Check concurrent limit
                in_progress = 1 if self.queue.in_progress else 0
                if in_progress >= self.config["max_concurrent"]:
                    await asyncio.sleep(5)
                    continue
                    
                # Process evolution
                await self._process_evolution(evolution)
                
            except Exception as e:
                self.logger.error(f"Process loop error: {e}")
                await asyncio.sleep(10)

    async def _process_evolution(self, evolution: QueuedEvolution):
        """Process a single evolution"""
        correlation_id = CorrelationContext.generate_id()
        CorrelationContext.set_id(correlation_id)
        
        self.logger.info(f"Processing evolution for {evolution.tool_name} (priority: {evolution.priority_score:.1f})")
        kind = (evolution.metadata or {}).get("kind", "evolve_tool")
        trace_type = "creation" if kind == "create_tool" else "evolution"
        broadcast_trace_sync(
            trace_type,
            f"Processing {evolution.tool_name}",
            "in_progress",
            {
                "stage": "queued_item",
                "tool_name": evolution.tool_name,
                "kind": kind,
                "priority_score": evolution.priority_score,
                "reason": evolution.reason,
            },
        )
        
        try:
            # Mark as in progress
            self.queue.mark_in_progress(evolution.tool_name)
            
            if kind == "create_tool":
                if not hasattr(self, "tool_creation_flow") or self.tool_creation_flow is None:
                    from domain.services.capability_graph import CapabilityGraph
                    from application.services.expansion_mode import ExpansionMode
                    from application.use_cases.tool_lifecycle.tool_creation_flow import ToolCreationOrchestrator
                    from application.services.skill_registry import SkillRegistry as _SR
                    _sr = _SR()
                    _sr.load_all()
                    self.tool_creation_flow = ToolCreationOrchestrator(
                        CapabilityGraph(),
                        ExpansionMode(enabled=True),
                        skill_registry=_sr,
                        llm_client=self.llm_client,
                    )

                gap_description = (evolution.metadata or {}).get("gap_description") or evolution.reason
                preferred_name = None
                gap_capability = (evolution.metadata or {}).get("gap_capability")
                if gap_capability:
                    preferred_name = (
                        (evolution.metadata or {}).get("preferred_name")
                        or "".join([p.capitalize() for p in str(gap_capability).split("_")]) + "Tool"
                    )

                result = await asyncio.to_thread(
                    self.tool_creation_flow.create_tool,
                    gap_description,
                    self.llm_client,
                    preferred_name,
                )
                if isinstance(result, tuple):
                    success, message = result
                    result = {"success": success, "message": message}
                tool_name_for_tests = None
                try:
                    tool_name_for_tests = (self.tool_creation_flow.last_spec or {}).get("name")
                except Exception:
                    tool_name_for_tests = None
                if result.get("success"):
                    pending_tool_id = self._persist_created_tool_for_approval(
                        evolution=evolution,
                        created_tool_name=tool_name_for_tests,
                        gap_description=gap_description,
                    )
                    if pending_tool_id:
                        result["pending_tool_id"] = pending_tool_id
                        result["status"] = "pending_approval"
                        broadcast_trace_sync(
                            "creation",
                            f"{tool_name_for_tests or evolution.tool_name} queued for approval",
                            "in_progress",
                            {
                                "stage": "pending_approval",
                                "tool_name": tool_name_for_tests or evolution.tool_name,
                                "pending_tool_id": pending_tool_id,
                            },
                        )
                # Feedback loop: record resolved gap in cua.db
                if result.get("success"):
                    gap_capability = (evolution.metadata or {}).get("gap_capability")
                    if gap_capability:
                        try:
                            from infrastructure.persistence.sqlite.cua_database import get_conn as _gcua
                            from datetime import datetime as _dt, timezone as _tz
                            with _gcua() as _c:
                                _c.execute(
                                    "INSERT INTO resolved_gaps (capability, resolution_action, tool_name, resolved_at, notes) VALUES (?,?,?,?,?)",
                                    (gap_capability, "create_tool", tool_name_for_tests or evolution.tool_name,
                                     _dt.now(_tz.utc).isoformat(), evolution.reason or ""),
                                )
                        except Exception as _fe:
                            self.logger.warning(f"Failed to record resolved gap: {_fe}")
            else:
                # Run evolution flow with execution context for skill-aware guidance
                # Build skill context for auto-triggered evolution
                execution_context = self._build_execution_context_for_auto_evolution(
                    evolution.tool_name,
                    evolution
                )
                
                # Determine auto_approve flag based on test score expectation
                # High-quality enhancements can be auto-approved if tests pass
                should_auto_approve = (
                    (evolution.metadata or {}).get("is_enhancement") and 
                    self.config.get("auto_approve_threshold", 90) >= 80
                )
                
                result = await asyncio.to_thread(
                    self.evolution_flow.evolve_tool,
                    evolution.tool_name,
                    evolution.reason,
                    should_auto_approve,
                    execution_context
                )
                if isinstance(result, tuple):
                    success, message = result
                    result = {"success": success, "message": message}
                tool_name_for_tests = evolution.tool_name
            
            # result is now always a dict
            
            if not result.get("success"):
                broadcast_trace_sync(
                    trace_type,
                    f"{evolution.tool_name} failed: {result.get('message', 'Unknown error')}",
                    "error",
                    {"stage": "result", "tool_name": evolution.tool_name, "kind": kind},
                )
                self.queue.mark_failed(evolution.tool_name, result.get("message", "Unknown error"))
                return
                
            # Run LLM tests (best-effort) — score is informational only;
            # test orchestrator runs without a live LLM so score is often 0
            test_target = tool_name_for_tests or evolution.tool_name
            test_result = self.test_orchestrator.run_test_suite(test_target)
            broadcast_trace_sync(
                trace_type,
                f"{test_target} ready for review",
                "success",
                {"stage": "result", "tool_name": test_target, "kind": kind, "result": result},
            )
            test_score = test_result.get("overall_score", 0)
            
            # Auto-approve evolution if test score meets threshold (creation always needs human)
            if kind == "evolve_tool" and test_score >= self.config["auto_approve_threshold"]:
                self.logger.info(f"Auto-approving evolution for {evolution.tool_name} (score={test_score})")
                try:
                    from application.managers.pending_evolutions_manager import PendingEvolutionsManager
                    mgr = PendingEvolutionsManager()
                    if mgr.get_pending_evolution(evolution.tool_name):
                        mgr.approve_evolution(evolution.tool_name)
                        result["auto_approved"] = True
                        broadcast_trace_sync("evolution", f"Auto-approved {evolution.tool_name}", "success",
                                             {"stage": "auto_approve", "test_score": test_score})
                except Exception as _e:
                    self.logger.warning(f"Auto-approve failed for {evolution.tool_name}: {_e}")
                    result["auto_approve_recommended"] = True
            elif kind == "create_tool":
                result["auto_approve_recommended"] = test_score >= self.config["auto_approve_threshold"]

            self.queue.mark_completed(evolution.tool_name)

            # Learn from result if enabled
            if self.config["learning_enabled"]:
                self._learn_from_evolution(evolution, result, test_score)
                
        except Exception as e:
            self.logger.error(f"Evolution processing error for {evolution.tool_name}: {e}")
            self.queue.mark_failed(evolution.tool_name, str(e))

    def _persist_created_tool_for_approval(
        self,
        evolution: QueuedEvolution,
        created_tool_name: Optional[str],
        gap_description: str,
    ) -> Optional[str]:
        """Persist successful autonomous creations into the pending-tools approval flow."""
        tool_name = created_tool_name or str((evolution.metadata or {}).get("preferred_name") or "").strip()
        if not tool_name:
            return None

        tool_file = Path("tools/experimental") / f"{tool_name}.py"
        test_file = Path("tests/experimental") / f"test_{tool_name}.py"
        if not tool_file.exists():
            self.logger.warning("Created tool file not found for pending approval: %s", tool_file)
            return None

        from application.managers.pending_tools_manager import PendingToolsManager

        pending_manager = PendingToolsManager()
        valid, contract_error = pending_manager.validate_tool_file_contract(str(tool_file).replace("\\", "/"))
        if not valid:
            self.logger.warning(
                "Autonomous tool creation produced invalid pending tool %s: %s",
                tool_name,
                contract_error,
            )
            return None

        existing = next(
            (
                item for item in pending_manager.get_pending_list()
                if str(item.get("tool_file", "")).replace("\\", "/") == str(tool_file).replace("\\", "/")
            ),
            None,
        )
        if existing:
            return existing.get("tool_id")

        return pending_manager.add_pending_tool(
            {
                "tool_file": str(tool_file).replace("\\", "/"),
                "test_file": str(test_file).replace("\\", "/") if test_file.exists() else None,
                "description": gap_description,
                "target_skill": (evolution.metadata or {}).get("target_skill"),
                "target_category": (evolution.metadata or {}).get("target_category"),
                "skill_updates": getattr(self.tool_creation_flow, "last_skill_updates", []),
                "risk_score": "low",
                "is_new_tool": True,
                "source": "coordinated_autonomy",
                "requested_capability": (evolution.metadata or {}).get("gap_capability"),
            }
        )

    def _build_execution_context_for_auto_evolution(self, tool_name: str, evolution: QueuedEvolution) -> Optional[SkillExecutionContext]:
        """Build SkillExecutionContext for auto-triggered tool evolutions."""
        try:
            # Step 1: Infer skill from tool name
            skill_contract = infer_skill_contract_for_tool(tool_name)
            
            if not skill_contract:
                self.logger.debug(f"No skill contract found for {tool_name}, using defaults")
                return SkillExecutionContext(
                    skill_name="general",
                    category="general",
                    verification_mode="output_validation",
                    risk_level="medium",
                    fallback_strategy="fail_fast",
                    expected_output_types=[],
                    max_retries=3,
                )
            
            # Step 2: Load skill definition for full context
            skill_registry = SkillRegistry()
            skill_registry.load_all()
            skill_name = skill_contract.get("target_skill")
            skill_definition = skill_registry.get(skill_name) if skill_name else None
            
            # Step 3: Create execution context with skill guidance
            execution_context = SkillExecutionContext(
                skill_name=skill_name or "general",
                category=skill_contract.get("target_category", "general"),
                skill_definition=skill_definition,
                verification_mode=skill_contract.get("verification_mode", "output_validation"),
                risk_level=skill_definition.risk_level if skill_definition else "medium",
                fallback_strategy=skill_definition.fallback_strategy if skill_definition else "fail_fast",
                preferred_tools=skill_definition.preferred_tools if skill_definition else [],
                expected_output_types=skill_contract.get("output_types", []),
            )
            
            # Step 4: Add evolution metadata for improved reasoning
            evolution_reason = evolution.reason or ""
            evolution_metadata = evolution.metadata or {}
            
            context_hints = []
            if evolution_metadata.get("category") == "WEAK":
                context_hints.append("Tool has critical issues that need fixing")
            elif evolution_metadata.get("category") == "NEEDS_IMPROVEMENT":
                context_hints.append("Tool needs improvements to be more reliable")
            elif evolution_metadata.get("is_enhancement"):
                context_hints.append("Tool is healthy but has enhancement opportunities")
            
            if evolution_metadata.get("issues_count", 0) > 0:
                context_hints.append(f"LLM identified {evolution_metadata['issues_count']} issues")
            
            if context_hints:
                execution_context.add_step(
                    tool=tool_name,
                    operation="auto_evolution_context",
                    status="prepared",
                    duration=0.0,
                    result={"reason": evolution_reason, "context": context_hints}
                )
            
            self.logger.info(
                f"Built execution context for {tool_name}: skill={skill_name}, "
                f"category={skill_contract.get('target_category')}, "
                f"verification_mode={execution_context.verification_mode}"
            )
            
            return execution_context
            
        except Exception as e:
            self.logger.error(f"Failed to build execution context for {tool_name}: {e}")
            return None

    def _learn_from_evolution(self, evolution: QueuedEvolution, result: Dict, test_score: float):
        """Record evolution outcome to improvement_memory.db for future threshold adjustment."""
        try:
            from infrastructure.persistence.file_storage.improvement_memory import ImprovementMemory
            mem = ImprovementMemory()
            kind = (evolution.metadata or {}).get("kind", "evolve_tool")
            mem.store_attempt(
                file_path=evolution.tool_name,
                change_type=kind,
                description=evolution.reason or "",
                patch="",
                outcome="success" if result.get("success") else "failed",
                error_message=result.get("message") if not result.get("success") else None,
                test_results={"overall_score": test_score, "auto_approved": result.get("auto_approved", False)},
                metrics={"priority_score": evolution.priority_score, "test_score": test_score},
            )
        except Exception as _e:
            self.logger.warning(f"Failed to record improvement memory: {_e}")
