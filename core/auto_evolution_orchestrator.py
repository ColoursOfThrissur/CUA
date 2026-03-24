"""
Auto-Evolution Orchestrator - Main engine for automatic tool improvements
"""
import asyncio
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from core.tool_quality_analyzer import ToolQualityAnalyzer
from core.llm_tool_health_analyzer import LLMToolHealthAnalyzer
from core.tool_evolution.flow import ToolEvolutionOrchestrator
from core.evolution_queue import EvolutionQueue, QueuedEvolution
from core.llm_test_orchestrator import LLMTestOrchestrator
from core.sqlite_logging import SQLiteLogger
from core.correlation_context import CorrelationContext
from core.skills.execution_context import SkillExecutionContext
from core.architecture_contract import derive_skill_contract_for_tool
from core.skills.registry import SkillRegistry
from api.trace_ws import broadcast_trace_sync

class AutoEvolutionOrchestrator:
    def __init__(self, llm_client=None, registry=None):
        self.quality_analyzer = ToolQualityAnalyzer()
        self.llm_health_analyzer = LLMToolHealthAnalyzer()
        self.evolution_flow = None
        self.queue = EvolutionQueue()
        self.test_orchestrator = None
        self.logger = SQLiteLogger()
        self.running = False
        self.scanning = False
        self.scan_progress = {"current": 0, "total": 0, "tool": ""}
        self.llm_client = llm_client
        self.registry = registry
        self.config = {
            "mode": "balanced",  # reactive, proactive, balanced, experimental
            "scan_interval": 3600,  # 1 hour
            "max_concurrent": 2,
            "min_health_threshold": 50,
            "auto_approve_threshold": 90,  # Auto-approve if test score >= 90
            "learning_enabled": True,
            "enable_enhancements": True,  # Queue tools with improvement suggestions
            "max_new_tools_per_scan": 1,  # Limit self-feature growth per scan
        }

    async def ensure_initialized(self):
        """Initialize dependent sub-systems without starting background loops."""
        if not self.llm_client or not self.registry:
            raise ValueError("LLM client and registry required")
        if not self.test_orchestrator:
            self.test_orchestrator = LLMTestOrchestrator(self.llm_client, self.registry)
        if not self.evolution_flow:
            from core.expansion_mode import ExpansionMode
            self.evolution_flow = ToolEvolutionOrchestrator(
                quality_analyzer=self.quality_analyzer,
                expansion_mode=ExpansionMode(enabled=True),
                llm_client=self.llm_client
            )

    async def run_cycle(self, max_items: Optional[int] = None) -> Dict:
        """Run a single scan-and-process cycle without background loops."""
        await self.ensure_initialized()
        broadcast_trace_sync("auto", "Auto-evolution scan starting", "in_progress", {"stage": "scan_start"})
        self.queue.clear_queue()
        await self._scan_and_queue()
        processed = 0
        failures = 0
        limit = max_items if max_items is not None else len(self.queue.queue)
        while processed < limit:
            evolution = self.queue.get_next()
            if not evolution:
                break
            await self._process_evolution(evolution)
            processed += 1
            if self.queue.failed.get(evolution.tool_name):
                failures += 1
        return {
            "scanned": True,
            "processed": processed,
            "failures": failures,
            "remaining_queue": len(self.queue.queue),
        }
        
    async def start(self):
        """Start auto-evolution engine"""
        await self.ensure_initialized()
        
        self.running = True
        self.logger.info(f"Auto-evolution orchestrator started (mode: {self.config['mode']})")
        
        # Start background tasks
        asyncio.create_task(self._scan_loop())
        asyncio.create_task(self._process_loop())
        
    async def stop(self):
        """Stop auto-evolution engine"""
        self.running = False
        self.logger.info("Auto-evolution orchestrator stopped")
        
    async def _scan_loop(self):
        """Periodically scan tools and queue evolutions"""
        while self.running:
            try:
                correlation_id = CorrelationContext.generate_id()
                CorrelationContext.set_id(correlation_id)
                
                await self._scan_and_queue()
                await asyncio.sleep(self.config["scan_interval"])
            except Exception as e:
                self.logger.error(f"Scan loop error: {e}")
                await asyncio.sleep(60)
                
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
                
    async def _scan_and_queue(self):
        """Scan tools with LLM health analysis and queue improvements"""
        self.scanning = True
        self.logger.info("Starting LLM-based tool health scan")
        
        try:
            # 0) Queue evolutions based on real usage signals (tool execution logs)
            try:
                weak_reports = self.quality_analyzer.get_weak_tools(days=7, min_usage=3)
                for report in weak_reports[:10]:
                    evolution = QueuedEvolution(
                        tool_name=report.tool_name,
                        urgency_score=90.0 if report.has_recent_errors else 70.0,
                        impact_score=self._calculate_impact({"usage_count": report.usage_frequency}),
                        feasibility_score=70.0,
                        timing_score=80.0,
                        reason=f"Low health score ({report.health_score:.1f}) - {', '.join(report.issues[:2])}",
                        metadata={"kind": "evolve_tool", "source": "quality_analyzer"},
                    )
                    self.queue.add(evolution)
            except Exception as e:
                self.logger.warning(f"Usage-based queueing skipped: {e}")

            # 1) Queue new tool creation from persistent capability gaps (self-feature growth)
            try:
                from core.gap_tracker import GapTracker
                tracker = GapTracker()
                actionable = tracker.get_actionable_gaps()
                max_new_tools = int(self.config.get("max_new_tools_per_scan", 1))
                created = 0
                for gap in actionable:
                    if created >= max_new_tools:
                        break
                    if gap.capability and not self.queue.is_queued(f"CREATE::{gap.capability}"):
                        evolution = QueuedEvolution(
                            tool_name=f"CREATE::{gap.capability}",
                            urgency_score=60.0,
                            impact_score=50.0,
                            feasibility_score=65.0,
                            timing_score=70.0,
                            reason=f"Persistent capability gap: {gap.capability} ({gap.occurrence_count}x, conf {gap.confidence_avg:.2f})",
                            metadata={
                                "kind": "create_tool",
                                "gap_capability": gap.capability,
                                "gap_description": f"Add capability: {gap.capability}. Reasons: {', '.join(gap.reasons[:3])}",
                                "suggested_library": gap.suggested_library,
                            },
                        )
                        self.queue.add(evolution)
                        created += 1
            except Exception as e:
                self.logger.warning(f"Gap-based tool creation queueing skipped: {e}")

            from pathlib import Path
            tools_dir = Path("tools/experimental")
            if not tools_dir.exists():
                self.logger.warning("No experimental tools directory found")
                return
            
            # Get all tool files
            tool_files = [f for f in tools_dir.glob("*.py") if not f.name.startswith("__")]
            self.scan_progress["total"] = len(tool_files)
            self.scan_progress["current"] = 0
            
            self.logger.info(f"Found {len(tool_files)} tools to analyze")
            
            # Run LLM analysis sequentially for each tool
            for tool_file in tool_files:
                tool_name = tool_file.stem
                self.scan_progress["current"] += 1
                self.scan_progress["tool"] = tool_name
                
                self.logger.info(f"Analyzing {tool_name} ({self.scan_progress['current']}/{self.scan_progress['total']})")
                self.logger.info(f"Checking if {tool_name} is already queued...")
                
                # Skip if already queued
                if self.queue.is_queued(tool_name):
                    self.logger.info(f"Skipping {tool_name} - already queued")
                    continue
                
                # Run LLM health analysis
                self.logger.info(f"Running LLM analysis for {tool_name}...")
                try:
                    llm_result = await asyncio.to_thread(
                        self.llm_health_analyzer.analyze_tool,
                        tool_name,
                        force_refresh=True
                    )
                    self.logger.info(f"LLM analysis complete for {tool_name}: category={llm_result.get('category', 'UNKNOWN')}, error={llm_result.get('error', 'None')}")
                except Exception as e:
                    self.logger.error(f"LLM analysis failed for {tool_name}: {e}")
                    continue
                
                if "error" in llm_result:
                    self.logger.warning(f"Skipping {tool_name}: {llm_result.get('error')}")
                    continue
                
                category = llm_result.get("category", "UNKNOWN")
                issues = llm_result.get("issues", [])
                improvements = llm_result.get("improvements", [])
                
                # Queue WEAK, NEEDS_IMPROVEMENT, or HEALTHY with improvements (if enabled)
                should_queue = False
                if category in ["WEAK", "NEEDS_IMPROVEMENT"]:
                    should_queue = True
                elif category == "HEALTHY" and len(improvements) > 0 and self.config.get("enable_enhancements", True):
                    should_queue = True
                
                if not should_queue:
                    continue
                
                # Calculate priority based on LLM analysis
                high_bugs = sum(1 for i in issues if i.get("severity") == "HIGH" and i.get("category") == "BUGS")
                high_priority_improvements = sum(1 for imp in improvements if imp.get("priority") == "HIGH")
                
                # Bugs get higher urgency than enhancements
                if category == "WEAK":
                    urgency = 100.0
                elif category == "NEEDS_IMPROVEMENT":
                    urgency = 75.0
                elif high_priority_improvements > 0:
                    urgency = 40.0  # Lower priority for enhancements
                else:
                    urgency = 25.0
                
                # Get execution metrics for impact
                exec_data = self.quality_analyzer.analyze_tool(tool_name)
                impact = self._calculate_impact({
                    "usage_count": exec_data.usage_frequency if exec_data else 0
                })
                
                feasibility = 80.0 if len(issues) > 0 else 60.0
                timing = 75.0  # Recent LLM analysis = good timing
                
                # Generate reason from LLM issues or improvements
                if category in ["WEAK", "NEEDS_IMPROVEMENT"]:
                    reason = self._generate_llm_reason(category, issues)
                else:
                    # Enhancement reason
                    high_imp = [imp for imp in improvements if imp.get("priority") == "HIGH"]
                    if high_imp:
                        reason = f"Enhancement opportunity: {high_imp[0].get('description', 'Add new features')}"
                    else:
                        reason = f"Feature enhancements suggested ({len(improvements)} improvements)"
                
                evolution = QueuedEvolution(
                    tool_name=tool_name,
                    urgency_score=urgency,
                    impact_score=impact,
                    feasibility_score=feasibility,
                    timing_score=timing,
                    reason=reason,
                    metadata={
                        "kind": "evolve_tool",
                        "category": category, 
                        "llm_scan": True, 
                        "issues_count": len(issues),
                        "improvements_count": len(improvements),
                        "is_enhancement": category == "HEALTHY"
                    }
                )
                self.queue.add(evolution)
                self.logger.info(f"Queued {tool_name} (priority: {evolution.priority_score:.1f}, category: {category})")
                
        except Exception as e:
            self.logger.error(f"Scan failed: {e}")
        finally:
            self.scanning = False
            self.scan_progress = {"current": 0, "total": 0, "tool": ""}
    
    def _build_execution_context_for_auto_evolution(self, tool_name: str, evolution: QueuedEvolution) -> Optional[SkillExecutionContext]:
        """Build SkillExecutionContext for auto-triggered tool evolutions.
        
        Auto-evolved tools need skill context to guide code generation and validation,
        similar to user-triggered evolutions.
        
        Args:
            tool_name: Name of the tool being evolved
            evolution: QueuedEvolution metadata
            
        Returns:
            SkillExecutionContext with skill-aware guidance, or None if unable to build
        """
        try:
            # Step 1: Infer skill from tool name
            skill_contract = derive_skill_contract_for_tool(tool_name)
            
            if not skill_contract:
                self.logger.debug(f"No skill contract found for {tool_name}, using defaults")
                # Tool not mapped to specific skill, use general context
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
            # Track why this evolution was triggered (quality issues, enhancements, etc.)
            evolution_reason = evolution.reason or ""
            evolution_metadata = evolution.metadata or {}
            
            # Build a helpful user_prompt style message from evolution metadata
            context_hints = []
            if evolution_metadata.get("category") == "WEAK":
                context_hints.append("Tool has critical issues that need fixing")
            elif evolution_metadata.get("category") == "NEEDS_IMPROVEMENT":
                context_hints.append("Tool needs improvements to be more reliable")
            elif evolution_metadata.get("is_enhancement"):
                context_hints.append("Tool is healthy but has enhancement opportunities")
            
            if evolution_metadata.get("issues_count", 0) > 0:
                context_hints.append(f"LLM identified {evolution_metadata['issues_count']} issues")
            
            # Add context hints to execution context via step history for tracing
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
                    from core.capability_graph import CapabilityGraph
                    from core.expansion_mode import ExpansionMode
                    from core.tool_creation.flow import ToolCreationOrchestrator
                    self.tool_creation_flow = ToolCreationOrchestrator(CapabilityGraph(), ExpansionMode(enabled=True))

                gap_description = (evolution.metadata or {}).get("gap_description") or evolution.reason
                preferred_name = None
                gap_capability = (evolution.metadata or {}).get("gap_capability")
                if gap_capability:
                    preferred_name = "".join([p.capitalize() for p in str(gap_capability).split("_")]) + "Tool"

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
                
            # Run LLM tests (best-effort)
            test_target = tool_name_for_tests or evolution.tool_name
            test_result = self.test_orchestrator.run_test_suite(test_target)
            broadcast_trace_sync(
                trace_type,
                f"{test_target} ready for review",
                "success",
                {"stage": "result", "tool_name": test_target, "kind": kind, "result": result},
            )
            test_score = test_result.get("overall_score", 0)
            
            self.logger.info(f"Evolution test score: {test_score} (tool: {test_target}, pass_rate: {test_result.get('pass_rate', 0)})")
            
            # Auto-approve if score is high enough
            if test_score >= self.config["auto_approve_threshold"]:
                self.logger.info(f"Auto-approving evolution for {evolution.tool_name}")
                # Note: Actual approval still requires human confirmation
                # This just marks it as recommended for auto-approval
                result["auto_approve_recommended"] = True
                
            self.queue.mark_completed(evolution.tool_name)
            
            # Learn from result if enabled
            if self.config["learning_enabled"]:
                self._learn_from_evolution(evolution, result, test_score)
                
        except Exception as e:
            self.logger.error(f"Evolution processing error for {evolution.tool_name}: {e}")
            self.queue.mark_failed(evolution.tool_name, str(e))
            
    def _calculate_urgency(self, health_data: Dict) -> float:
        """Calculate urgency score (0-100)"""
        health = health_data.get("health_score", 100)
        recent_errors = health_data.get("recent_errors", 0)
        
        # Critical if health < 30 or many recent errors
        if health < 30 or recent_errors > 10:
            return 100.0
        elif health < 50 or recent_errors > 5:
            return 75.0
        elif health < 70:
            return 50.0
        else:
            return 25.0
            
    def _calculate_impact(self, health_data: Dict) -> float:
        """Calculate impact score (0-100)"""
        usage = health_data.get("usage_count", 0)
        
        # High usage = high impact
        if usage > 100:
            return 100.0
        elif usage > 50:
            return 75.0
        elif usage > 10:
            return 50.0
        else:
            return 25.0
            
    def _calculate_feasibility(self, health_data: Dict) -> float:
        """Calculate feasibility score (0-100)"""
        # Simple heuristic: tools with clear issues are easier to fix
        issues = health_data.get("issues", [])
        
        # Issues are strings, not dicts - just count them
        if len(issues) > 2:
            return 80.0  # Multiple clear issues = easier to fix
        elif len(issues) > 0:
            return 60.0
        else:
            return 40.0  # No clear issues = harder to improve
            
    def _calculate_timing(self, health_data: Dict) -> float:
        """Calculate timing score (0-100)"""
        last_execution = health_data.get("last_execution")
        if not last_execution:
            return 50.0
            
        # Recent activity = better timing
        hours_since = (datetime.now() - datetime.fromisoformat(last_execution)).total_seconds() / 3600
        
        if hours_since < 1:
            return 100.0
        elif hours_since < 24:
            return 75.0
        elif hours_since < 168:  # 1 week
            return 50.0
        else:
            return 25.0
            
    def _should_queue(self, health_score: float, urgency: float, impact: float) -> bool:
        """Determine if tool should be queued based on mode"""
        mode = self.config["mode"]
        
        if mode == "reactive":
            # Only queue if health is below threshold
            return health_score < self.config["min_health_threshold"]
            
        elif mode == "proactive":
            # Queue if health is not perfect or high impact
            return health_score < 95 or impact > 70
            
        elif mode == "balanced":
            # Queue if health is low OR (medium health + high urgency/impact)
            return (health_score < 70 or 
                   (health_score < 85 and (urgency > 60 or impact > 60)))
                   
        elif mode == "experimental":
            # Queue everything for continuous improvement
            return True
            
        return False
        
    def _generate_reason(self, health_data: Dict) -> str:
        """Generate human-readable reason for evolution"""
        health = health_data.get("health_score", 0)
        errors = health_data.get("recent_errors", 0)
        
        if health < 30:
            return f"Critical health score ({health}/100) - immediate attention required"
        elif errors > 5:
            return f"High error rate ({errors} recent errors) - stability improvement needed"
        elif health < 70:
            return f"Below target health ({health}/100) - optimization recommended"
        else:
            return "Proactive improvement opportunity detected"
    
    def _generate_llm_reason(self, category: str, issues: List[Dict]) -> str:
        """Generate reason from LLM analysis"""
        if category == "WEAK":
            high_bugs = [i for i in issues if i.get("severity") == "HIGH" and i.get("category") == "BUGS"]
            if high_bugs:
                return f"Critical code issues detected: {high_bugs[0].get('description', 'Unknown')}"
            return f"Multiple code quality issues found ({len(issues)} issues)"
        elif category == "NEEDS_IMPROVEMENT":
            return f"Code quality improvements needed ({len(issues)} issues identified)"
        return "LLM analysis recommends improvements"
            
    def _learn_from_evolution(self, evolution: QueuedEvolution, result: Dict, test_score: float):
        """Learn from evolution outcome to improve future prioritization"""
        # Store learning data for future analysis
        learning_data = {
            "tool_name": evolution.tool_name,
            "priority_score": evolution.priority_score,
            "test_score": test_score,
            "success": result.get("success", False),
            "timestamp": datetime.now().isoformat()
        }
        self.logger.debug(f"Learning from evolution: {learning_data}")
        
    def update_config(self, config: Dict):
        """Update orchestrator configuration"""
        self.config.update(config)
        self.logger.info(f"Configuration updated: {config}")
        
    def get_status(self) -> Dict:
        """Get orchestrator status"""
        return {
            "running": self.running,
            "scanning": self.scanning,
            "scan_progress": self.scan_progress if self.scanning else None,
            "mode": self.config["mode"],
            "queue_size": len(self.queue.queue),
            "in_progress": 1 if self.queue.in_progress else 0,
            "config": self.config
        }
