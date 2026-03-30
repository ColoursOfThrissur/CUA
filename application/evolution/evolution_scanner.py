"""
Evolution Scanner - Scans for tools that need improvement and queues them for evolution.
"""
import asyncio
from typing import Dict, List
from domain.services.tool_quality_analyzer import ToolQualityAnalyzer
from infrastructure.analysis.llm_tool_health_analyzer import LLMToolHealthAnalyzer
from application.use_cases.evolution.evolution_queue import EvolutionQueue, QueuedEvolution
from infrastructure.persistence.sqlite.logging import SQLiteLogger
from shared.utils.correlation_context import CorrelationContext

class EvolutionScanner:
    def __init__(self, logger: SQLiteLogger, llm_client, registry, quality_analyzer: ToolQualityAnalyzer, llm_health_analyzer: LLMToolHealthAnalyzer, queue: EvolutionQueue, config: Dict):
        self.logger = logger
        self.llm_client = llm_client
        self.registry = registry
        self.quality_analyzer = quality_analyzer
        self.llm_health_analyzer = llm_health_analyzer
        self.queue = queue
        self.config = config
        self.running = False
        self.scanning = False
        self.scan_progress = {"current": 0, "total": 0, "tool": ""}
        self._DISABLED_TOOLS = {"TaskBreakdownTool", "DatabaseQueryTool"}

    async def start(self):
        self.running = True
        self.logger.info("Evolution scanner started")
        asyncio.create_task(self._scan_loop())

    async def stop(self):
        self.running = False
        self.logger.info("Evolution scanner stopped")

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

    async def _scan_and_queue(self):
        """Scan tools with LLM health analysis and queue improvements"""
        self.scanning = True
        self.logger.info("Starting LLM-based tool health scan")
        
        try:
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
                from domain.services.gap_tracker import GapTracker
                from domain.services.gap_detector import GapDetector
                from application.services.capability_mapper import CapabilityMapper
                tracker = GapTracker()

                # LLM-driven gap analysis over recent failed requests
                try:
                    from infrastructure.persistence.sqlite.cua_database import get_conn as _get_cua_conn
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
                    from application.use_cases.tool_lifecycle.tool_registry_manager import ToolRegistryManager
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

    def _recently_evolved_insufficient_data(self, tool_name: str, min_executions: int = 3) -> bool:
        """Return True if the tool was successfully evolved recently but hasn't been
        executed enough times since to produce meaningful health data, OR if it was
        evolved within the cooldown window (prevents churn on active tools).
        """
        COOLDOWN_HOURS = 6  # minimum hours between evolutions of the same tool
        try:
            from infrastructure.persistence.sqlite.cua_database import get_conn
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

