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
            "enable_enhancements": True,  # Queue HEALTHY tools with improvements too
            "max_new_tools_per_scan": 3,  # tools to create per scan from gaps
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
                
    async def _analyze_system_gaps(self):
        """Proactively reason about the full CUA system and identify missing tools.
        Reads skills, existing tools, and architecture to find capability gaps
        without waiting for user failures to trigger them.
        """
        try:
            from pathlib import Path
            from core.gap_tracker import GapTracker
            from core.gap_detector import CapabilityGap

            # Build system snapshot: skills and what they need
            skills_snapshot = []
            skills_dir = Path("skills")
            for skill_dir in sorted(skills_dir.iterdir()):
                skill_json = skill_dir / "skill.json"
                if not skill_json.exists():
                    continue
                try:
                    import json as _json
                    skill_def = _json.loads(skill_json.read_text())
                    skills_snapshot.append({
                        "name": skill_def.get("name", skill_dir.name),
                        "description": skill_def.get("description", ""),
                        "preferred_tools": skill_def.get("preferred_tools", []),
                        "capabilities_needed": skill_def.get("capabilities", []),
                    })
                except Exception:
                    pass

            # Build existing tool inventory
            existing_tools = []
            for tools_path in [Path("tools"), Path("tools/experimental")]:
                if not tools_path.exists():
                    continue
                for tf in tools_path.glob("*.py"):
                    if tf.name.startswith("__"):
                        continue
                    existing_tools.append(tf.stem)

            # Build covered capabilities from registry
            covered_caps = set()
            if self.registry:
                try:
                    for tool in getattr(self.registry, "tools", []):
                        for cap_name in (tool.get_capabilities() or {}):
                            covered_caps.add(cap_name.lower())
                        covered_caps.add(tool.__class__.__name__.lower().replace("tool", ""))
                except Exception:
                    pass

            import json as _json
            system_context = (
                "You are analyzing the CUA autonomous agent system to find missing tool capabilities.\n"
                "CUA is a local autonomous agent: plans tasks, routes via skills, calls tools, creates/evolves tools.\n\n"
                f"SKILLS: {', '.join(s['name'] for s in skills_snapshot)}\n"
                f"EXISTING TOOLS: {', '.join(existing_tools)}\n"
                f"COVERED CAPABILITIES (sample): {', '.join(sorted(covered_caps)[:30])}\n\n"
                "What tool capabilities are clearly missing for a general-purpose autonomous agent?\n"
                "Consider: what each skill needs, what gaps exist between skills and tools.\n\n"
                "Return JSON array of up to 3 gaps (most impactful first):\n"
                '[{"capability": "short_name", "confidence": 0.0-1.0, "reason": "max 8 words", '
                '"suggested_tool_name": "ToolNameTool"}]\n'
                "Only include gaps where confidence >= 0.75. Keep reason under 8 words. If nothing is missing return []"
            )

            raw = await asyncio.to_thread(
                self.llm_client._call_llm,
                system_context,
                0.1,
                800,  # was 300 — too small for JSON array with reason strings, caused truncation
                True,
            )
            import json as _json
            data = _json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(data, list):
                return

            tracker = GapTracker()
            found = 0
            for item in data:
                cap = (item.get("capability") or "").strip()
                conf = float(item.get("confidence", 0.0))
                reason = (item.get("reason") or "").strip()
                suggested_name = (item.get("suggested_tool_name") or "").strip()
                if not cap or conf < 0.75:
                    continue
                # Skip if already covered — exact match only
                cap_key = cap.lower().replace(":", "_")
                if cap_key in covered_caps:
                    continue
                # Skip if already tracked and actionable
                existing = tracker.gaps.get(cap)
                if existing and existing.resolution_attempted:
                    continue
                gap = CapabilityGap(
                    capability=cap,
                    confidence=min(conf, 0.95),
                    reason=reason,
                    domain="system_analysis",
                    gap_type="llm_identified",
                    suggested_action="create_tool",
                )
                if suggested_name:
                    gap.target_tool = suggested_name
                tracker.record_gap(gap)
                found += 1
                self.logger.info(f"System gap identified: {cap} (conf={conf:.2f}) — {reason}")
                broadcast_trace_sync("auto", f"System gap found: {cap}", "in_progress",
                                     {"stage": "system_analysis", "capability": cap, "confidence": conf})

            if found:
                self.logger.info(f"System analysis found {found} new capability gaps")
        except Exception as e:
            self.logger.warning(f"System gap analysis skipped: {e}")

    async def _scan_and_queue(self):
        """Scan tools with LLM health analysis and queue improvements"""
        self.scanning = True
        self.logger.info("Starting LLM-based tool health scan")
        
        try:
            # 0) Proactive system-wide gap analysis — LLM reasons about full CUA architecture
            # System gap analysis now runs in CoordinatedAutonomyEngine._proactive_gap_analysis
            # every cycle with results fed directly into tool creation.
            # Removed from here to avoid running the same LLM call twice per cycle.

            # 1) Queue evolutions based on real usage signals (tool execution logs)
            try:
                weak_reports = self.quality_analyzer.get_weak_tools(days=7, min_usage=5)
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
                from core.gap_detector import GapDetector
                from core.capability_mapper import CapabilityMapper
                tracker = GapTracker()

                # LLM-driven gap analysis over recent failed requests
                try:
                    from core.cua_db import get_conn as _get_cua_conn
                    failed_requests = []
                    with _get_cua_conn() as _conn:
                        _rows = _conn.execute(
                            "SELECT failure_reason, error_message FROM failures "
                            "ORDER BY timestamp DESC LIMIT 20"
                        ).fetchall() or []
                        failed_requests = [
                            {"task": r[0] or "", "error": r[1] or ""} for r in _rows
                        ]
                    if failed_requests:
                        detector = GapDetector(CapabilityMapper())
                        llm_gap = detector.analyze_with_llm(failed_requests, self.llm_client)
                        if llm_gap and llm_gap.confidence >= 0.7:
                            tracker.record_gap(llm_gap)
                            self.logger.info(f"LLM gap analysis found: {llm_gap.capability} (conf={llm_gap.confidence:.2f})")
                except Exception as _ge:
                    self.logger.warning(f"LLM gap analysis skipped: {_ge}")

                actionable = tracker.get_actionable_gaps()
                max_new_tools = int(self.config.get("max_new_tools_per_scan", 1))
                created = 0

                # Build set of capability names already covered by loaded tools
                covered_caps: set = set()
                if self.registry:
                    try:
                        for tool in getattr(self.registry, "tools", []):
                            for cap_name in (tool.get_capabilities() or {}):
                                covered_caps.add(cap_name.lower())
                            covered_caps.add(tool.__class__.__name__.lower().replace("tool", ""))
                    except Exception:
                        pass

                for gap in actionable:
                    if created >= max_new_tools:
                        break
                    gap_key = (gap.capability or "").lower().replace(":", "_")
                    # Skip only if an exact capability name matches — not substring
                    # The old 'gap_key in cap or cap in gap_key' was too broad and
                    # filtered out almost everything via substring coincidence
                    if gap_key in covered_caps:
                        self.logger.info(f"Gap '{gap.capability}' already covered by loaded tool — skipping CREATE")
                        continue
                    if gap.capability and not self.queue.is_queued(f"CREATE::{gap.capability}"):
                        preferred_name = getattr(gap, "target_tool", None)
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
                                "preferred_name": preferred_name,
                            },
                        )
                        self.queue.add(evolution)
                        # Mark gap so it doesn't re-queue on the next scan
                        tracker.mark_resolved(gap.capability, "create_tool")
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
                
                # Skip disabled tools — they never execute so health never updates
                if tool_name in self._DISABLED_TOOLS:
                    self.logger.info(f"Skipping {tool_name} - disabled tool")
                    continue

                # Skip if already queued
                if self.queue.is_queued(tool_name):
                    self.logger.info(f"Skipping {tool_name} - already queued")
                    continue

                # Skip disabled tools — they never execute so health data never improves
                try:
                    from core.tool_registry_manager import ToolRegistryManager
                    if tool_name in ToolRegistryManager.DISABLED_TOOLS:
                        self.logger.info(f"Skipping {tool_name} - disabled tool")
                        continue
                except Exception:
                    pass

                # Skip if tool was recently evolved and hasn't been executed enough since
                if self._recently_evolved_insufficient_data(tool_name):
                    self.logger.info(f"Skipping {tool_name} - recently evolved, awaiting execution data")
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
                is_enhancement = category == "HEALTHY" and len(improvements) > 0
                should_queue = False
                if category in ["WEAK", "NEEDS_IMPROVEMENT"]:
                    should_queue = True
                elif is_enhancement and self.config.get("enable_enhancements", True):
                    # Cap enhancements per scan to avoid queuing all healthy tools
                    enhancement_queued = sum(1 for e in self.queue.queue if (e.metadata or {}).get("is_enhancement"))
                    if enhancement_queued < int(self.config.get("max_new_tools_per_scan", 3)):
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
                        "is_enhancement": is_enhancement
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
                    from core.skills.registry import SkillRegistry as _SR
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
                # Feedback loop: record resolved gap in cua.db
                if result.get("success"):
                    gap_capability = (evolution.metadata or {}).get("gap_capability")
                    if gap_capability:
                        try:
                            from core.cua_db import get_conn as _gcua
                            from datetime import datetime as _dt
                            with _gcua() as _c:
                                _c.execute(
                                    "INSERT INTO resolved_gaps (capability, resolution_action, tool_name, resolved_at, notes) VALUES (?,?,?,?,?)",
                                    (gap_capability, "create_tool", tool_name_for_tests or evolution.tool_name,
                                     _dt.utcnow().isoformat(), evolution.reason or ""),
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
                    from core.pending_evolutions_manager import PendingEvolutionsManager
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
            
    # Tools that are intentionally disabled and should never be re-queued for evolution
    _DISABLED_TOOLS = {"TaskBreakdownTool", "DatabaseQueryTool"}

    def _recently_evolved_insufficient_data(self, tool_name: str, min_executions: int = 3) -> bool:
        """Return True if the tool was successfully evolved recently but hasn't been
        executed enough times since to produce meaningful health data, OR if it was
        evolved within the cooldown window (prevents churn on active tools).
        """
        COOLDOWN_HOURS = 6  # minimum hours between evolutions of the same tool
        try:
            from core.cua_db import get_conn
            with get_conn() as conn:
                row = conn.execute(
                    """SELECT timestamp FROM evolution_runs
                       WHERE tool_name = ? AND status IN ('success', 'approved')
                       ORDER BY timestamp DESC LIMIT 1""",
                    (tool_name,)
                ).fetchone()
            if not row:
                return False
            last_evolved_at = row[0]
        except Exception:
            return False

        # Cooldown check — always skip if evolved within COOLDOWN_HOURS regardless of executions
        try:
            from datetime import datetime, timezone, timedelta
            last_dt = datetime.fromisoformat(last_evolved_at.replace('Z', '+00:00'))
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - last_dt < timedelta(hours=COOLDOWN_HOURS):
                return True
        except Exception:
            pass

        try:
            import sqlite3
            conn2 = sqlite3.connect("data/tool_executions.db")
            row2 = conn2.execute(
                "SELECT COUNT(*) FROM executions WHERE tool_name = ? AND timestamp > ?",
                (tool_name, last_evolved_at)
            ).fetchone()
            conn2.close()
            executions_since = row2[0] if row2 else 0
        except Exception:
            return False

        return executions_since < min_executions

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
        try:
            from datetime import timezone
            parsed = datetime.fromisoformat(str(last_execution).replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            hours_since = (now - parsed).total_seconds() / 3600
        except Exception:
            return 50.0
        if hours_since < 1:
            return 100.0
        elif hours_since < 24:
            return 75.0
        elif hours_since < 168:
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
        """Record evolution outcome to improvement_memory.db for future threshold adjustment."""
        try:
            from core.improvement_memory import ImprovementMemory
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
