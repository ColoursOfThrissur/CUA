"""Coordinated unattended autonomy engine for scheduled self-improvement cycles."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.baseline_health_checker import BaselineHealthChecker
from core.gap_tracker import GapTracker
from core.pending_evolutions_manager import PendingEvolutionsManager
from core.pending_tools_manager import PendingToolsManager
from core.tool_quality_analyzer import ToolQualityAnalyzer
from api.trace_ws import broadcast_trace_sync


class CoordinatedAutonomyEngine:
    """Coordinates health checks, gap review, auto-evolution, and bounded improvement loops."""

    def __init__(
        self,
        improvement_loop,
        llm_client,
        registry,
        auto_orchestrator=None,
    ):
        from core.auto_evolution_orchestrator import AutoEvolutionOrchestrator

        self.improvement_loop = improvement_loop
        self.llm_client = llm_client
        self.registry = registry
        self.auto_orchestrator = auto_orchestrator or AutoEvolutionOrchestrator(llm_client, registry)
        self.running = False
        self._task: Optional[asyncio.Task] = None
        self.last_cycle: Optional[Dict[str, Any]] = None
        self.last_error: Optional[str] = None
        self.cycle_count = 0
        self.consecutive_low_value_cycles = 0
        self.paused_reason: Optional[str] = None
        # Reuse managers — they are file-backed singletons
        self._pending_tools_manager = PendingToolsManager()
        self._pending_evolutions_manager = PendingEvolutionsManager()
        self._quality_analyzer = ToolQualityAnalyzer()
        self.config = {
            "interval_seconds": 30,
            "improvement_iterations_per_cycle": 3,
            "max_evolutions_per_cycle": 10,
            "dry_run": False,
            "min_usefulness_score": 0.35,
            "max_consecutive_low_value_cycles": 5,
            "pause_on_low_value": False,
        }

    async def start(self):
        if self.running:
            return {"success": False, "message": "Coordinator already running"}
        self.running = True
        self.paused_reason = None
        broadcast_trace_sync("auto", "Coordinated autonomy started", "success", {"stage": "start"})
        self._task = asyncio.create_task(self._run_loop())
        return {"success": True, "message": "Coordinator started"}

    async def stop(self):
        self.running = False
        broadcast_trace_sync("auto", "Coordinated autonomy stopped", "success", {"stage": "stop"})
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        return {"success": True, "message": "Coordinator stopped"}

    async def _run_loop(self):
        while self.running:
            started = time.time()
            try:
                broadcast_trace_sync("auto", "Starting coordinated cycle", "in_progress", {"stage": "cycle_start"})
                self.last_cycle = await self.run_cycle()
                self.last_error = None
                if self.last_cycle.get("quality_gate", {}).get("should_pause"):
                    self.paused_reason = self.last_cycle["quality_gate"].get("reason")
                    broadcast_trace_sync(
                        "auto",
                        f"Coordinated autonomy paused: {self.paused_reason}",
                        "error",
                        {"stage": "quality_gate", "quality_gate": self.last_cycle.get("quality_gate", {})},
                    )
                    self.running = False
                    break
            except Exception as exc:
                self.last_error = str(exc)
                self.last_cycle = {
                    "success": False,
                    "error": str(exc),
                    "finished_at": self._utc_now(),
                }
                broadcast_trace_sync("auto", f"Coordinated cycle failed: {exc}", "error", {"stage": "cycle_error"})
            if not self.running:
                break
            elapsed = time.time() - started
            sleep_for = max(5, self.config["interval_seconds"] - elapsed)
            next_run = datetime.now(timezone.utc).fromtimestamp(
                time.time() + sleep_for, tz=timezone.utc
            ).strftime("%H:%M UTC")
            broadcast_trace_sync(
                "auto",
                f"Cycle complete — next run in {int(sleep_for // 60)}m (at {next_run})",
                "success",
                {"stage": "sleeping", "sleep_seconds": sleep_for},
            )
            await asyncio.sleep(sleep_for)

    async def run_cycle(self):
        cycle_started_at = self._utc_now()
        broadcast_trace_sync("auto", "Running baseline health check", "in_progress", {"stage": "baseline"})
        baseline_ok, baseline_message, baseline_failures = BaselineHealthChecker().check_baseline()
        if not baseline_ok:
            result = {
                "success": False,
                "stage": "baseline",
                "baseline_ok": False,
                "baseline_message": baseline_message,
                "baseline_failures": baseline_failures[:10],
                "finished_at": self._utc_now(),
            }
            self.last_cycle = result
            broadcast_trace_sync(
                "auto",
                f"Baseline check failed: {baseline_message}",
                "error",
                {"stage": "baseline", "failures": baseline_failures[:10]},
            )
            return result

        tracker = GapTracker()
        prioritized_gaps = tracker.get_prioritized_gaps()
        broadcast_trace_sync(
            "auto",
            f"Gap review complete: {len(prioritized_gaps)} prioritized gaps",
            "in_progress",
            {"stage": "gap_review", "gap_count": len(prioritized_gaps)},
        )

        # Run CapabilityResolver on each gap — cheaper paths (reroute/MCP/API) take priority
        from core.capability_resolver import CapabilityResolver
        from core.gap_detector import CapabilityGap as _CG
        resolver = CapabilityResolver(registry=self.registry)
        for gap_record in prioritized_gaps:
            if gap_record.resolution_attempted:
                continue
            _gap = _CG(
                capability=gap_record.capability,
                confidence=gap_record.confidence_avg,
                reason=gap_record.reasons[0] if gap_record.reasons else "",
                domain=getattr(gap_record, "gap_type", "unknown"),
            )
            resolution = resolver.resolve(_gap)
            if resolution.resolved and resolution.action != "create_tool":
                tracker.mark_resolved(
                    gap_record.capability,
                    resolution.action,
                    target=resolution.target,
                    notes=resolution.notes,
                )
                broadcast_trace_sync(
                    "auto",
                    f"Gap '{gap_record.capability}' resolved via {resolution.action} → {resolution.target}",
                    "success",
                    {"stage": "gap_resolution", "capability": gap_record.capability, "action": resolution.action},
                )
        # Re-fetch after resolution pass — only unresolved create_tool gaps remain
        prioritized_gaps = tracker.get_prioritized_gaps()
        pending_before = self._collect_pending_counts()
        quality_before = self._collect_quality_summary()

        broadcast_trace_sync("auto", "Running auto-evolution pass", "in_progress", {"stage": "auto_evolution"})
        auto_result = await self.auto_orchestrator.run_cycle(
            max_items=self.config["max_evolutions_per_cycle"]
        )
        # Count only successful evolutions (processed minus failures) for metrics
        evolutions_succeeded = max(0, auto_result.get("processed", 0) - auto_result.get("failures", 0))

        # Tool creation phase — runs after evolution when the total pending
        # approval queue is below the cap (10). This prevents flooding the
        # queue when the user is away, while ensuring creation always gets
        # a turn as long as there is room.
        # The delta condition (new_evo_this_cycle == 0) was removed because
        # evolution always produces new pending items, permanently blocking
        # creation. The cap alone is the right throttle.
        CREATION_PENDING_CAP = 10
        pending_mid = self._collect_pending_counts()
        total_pending_now = pending_mid["pending_evolutions"] + pending_mid["pending_tools"]

        if total_pending_now < CREATION_PENDING_CAP:
            broadcast_trace_sync("auto", "Running tool creation phase", "in_progress", {"stage": "tool_creation"})
            creation_result = await self._run_creation_phase()
            if creation_result.get("queued"):
                broadcast_trace_sync(
                    "auto",
                    f"Tool creation: {creation_result['queued']} tool(s) queued",
                    "in_progress",
                    {"stage": "tool_creation", "queued": creation_result["queued"]},
                )
        else:
            creation_result = {
                "skipped": True,
                "reason": f"pending queue at cap ({total_pending_now}/{CREATION_PENDING_CAP}) — approve pending items first",
                "queued": 0,
            }
            broadcast_trace_sync(
                "auto",
                f"Tool creation skipped: queue full ({total_pending_now}/{CREATION_PENDING_CAP})",
                "in_progress",
                {"stage": "tool_creation"},
            )

        broadcast_trace_sync("auto", "Running self-improvement pass", "in_progress", {"stage": "improvement_loop"})
        loop_result = await self._run_improvement_pass(
            max_iterations=self.config["improvement_iterations_per_cycle"],
            dry_run=self.config["dry_run"],
        )
        pending_after = self._collect_pending_counts()
        quality_after = self._collect_quality_summary()
        quality_gate = self._evaluate_cycle_quality(
            gaps_count=len(prioritized_gaps),
            auto_result=auto_result,
            loop_result=loop_result,
            pending_before=pending_before,
            pending_after=pending_after,
            quality_before=quality_before,
            quality_after=quality_after,
        )

        self.cycle_count += 1
        result = {
            "success": True,
            "cycle_count": self.cycle_count,
            "started_at": cycle_started_at,
            "finished_at": self._utc_now(),
            "baseline_ok": True,
            "gap_summary": {
                "count": len(prioritized_gaps),
                "top_capabilities": [gap.capability for gap in prioritized_gaps[:5]],
            },
            "auto_evolution": auto_result,
            "tool_creation": creation_result,
            "improvement_loop": loop_result,
            "pending_summary": {
                "before": pending_before,
                "after": pending_after,
                "delta": {
                    "pending_tools": pending_after["pending_tools"] - pending_before["pending_tools"],
                    "pending_evolutions": pending_after["pending_evolutions"] - pending_before["pending_evolutions"],
                },
            },
            "quality_summary": {
                "before": quality_before,
                "after": quality_after,
            },
            "quality_gate": quality_gate,
        }
        self.last_cycle = result

        # Persist cycle summary to cua.db so UI cycle history survives restarts
        try:
            from core.cua_db import get_conn
            with get_conn() as conn:
                conn.execute(
                    """INSERT INTO auto_evolution_metrics
                       (hour_timestamp, tools_analyzed, evolutions_triggered,
                        evolutions_pending, evolutions_approved, evolutions_rejected,
                        avg_health_improvement, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        self._utc_now(),
                        quality_after.get("total_tools", 0),
                        evolutions_succeeded,
                        pending_after["pending_evolutions"] + pending_after["pending_tools"],
                        0,  # approved tracked separately via approval endpoints
                        auto_result.get("failures", 0),
                        quality_gate.get("avg_health_delta", 0.0),
                        self._utc_now(),
                    )
                )
        except Exception as _e:
            pass  # metrics persistence must never break the cycle
        broadcast_trace_sync(
            "auto",
            f"Coordinated cycle complete (score {quality_gate['score']})",
            "success" if not quality_gate.get("low_value") else "in_progress",
            {
                "stage": "cycle_complete",
                "quality_gate": quality_gate,
                "pending_summary": result["pending_summary"],
            },
        )
        return result

    async def _run_creation_phase(self) -> dict:
        """Queue tool creation for actionable gaps.

        Runs every cycle after evolution. Evolution improves existing tools;
        creation adds new ones. Both produce pending approvals the user reviews.
        The two queues are independent — creation does not wait for evolutions
        to be approved first. max_new_tools_per_scan caps tools created per cycle.
        """
        try:
            from core.gap_tracker import GapTracker
            tracker = GapTracker()
            actionable = tracker.get_actionable_gaps()
            create_gaps = [g for g in actionable if g.suggested_action == "create_tool"]

            if not create_gaps:
                return {"skipped": True, "reason": "No actionable create_tool gaps", "queued": 0}

            await self.auto_orchestrator.ensure_initialized()
            max_new = int(self.auto_orchestrator.config.get("max_new_tools_per_scan", 1))

            covered_caps: set = set()
            if self.registry:
                try:
                    for tool in getattr(self.registry, "tools", []):
                        for cap_name in (tool.get_capabilities() or {}):
                            covered_caps.add(cap_name.lower())
                        covered_caps.add(tool.__class__.__name__.lower().replace("tool", ""))
                except Exception:
                    pass

            from core.evolution_queue import QueuedEvolution
            queued = 0
            for gap in create_gaps:
                if queued >= max_new:
                    break
                gap_key = (gap.capability or "").lower().replace(":", "_")
                if gap_key in covered_caps:
                    continue
                tool_name = f"CREATE::{gap.capability}"
                if self.auto_orchestrator.queue.is_queued(tool_name):
                    continue
                preferred_name = getattr(gap, "target_tool", None)
                evolution = QueuedEvolution(
                    tool_name=tool_name,
                    urgency_score=70.0,
                    impact_score=60.0,
                    feasibility_score=65.0,
                    timing_score=75.0,
                    reason=f"Gap resolved via creation: {gap.capability} "
                           f"({gap.occurrence_count}x, conf {gap.confidence_avg:.2f})",
                    metadata={
                        "kind": "create_tool",
                        "gap_capability": gap.capability,
                        "gap_description": f"Add capability: {gap.capability}. "
                                           f"Reasons: {', '.join(gap.reasons[:3])}",
                        "preferred_name": preferred_name,
                    },
                )
                self.auto_orchestrator.queue.add(evolution)
                tracker.mark_resolved(gap.capability, "create_tool")
                queued += 1
                broadcast_trace_sync(
                    "auto",
                    f"Queued tool creation for gap: {gap.capability}",
                    "in_progress",
                    {"stage": "tool_creation", "capability": gap.capability},
                )

            if queued > 0:
                await self.auto_orchestrator.run_cycle(max_items=queued)

            return {"queued": queued, "gaps_checked": len(create_gaps)}

        except Exception as e:
            return {"skipped": True, "reason": str(e), "queued": 0}

    async def _run_improvement_pass(self, max_iterations: int, dry_run: bool):
        controller = self.improvement_loop.controller
        controller.max_iterations = max_iterations
        self.improvement_loop.dry_run = dry_run
        self.improvement_loop.continuous_mode = False
        start_result = await self.improvement_loop.start_loop()

        while self.improvement_loop.state.status.value in {"running", "stopping"}:
            await asyncio.sleep(0.5)

        return {
            "start_result": start_result,
            "status": self.improvement_loop.state.status.value,
            "iterations_completed": self.improvement_loop.state.current_iteration,
            "preview_count": len(getattr(self.improvement_loop.controller, "preview_proposals", [])),
        }

    def update_config(self, config: Dict[str, Any]):
        self.config.update({k: v for k, v in config.items() if v is not None})
        return self.config

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _collect_pending_counts(self) -> Dict[str, int]:
        try:
            pending_tools = len(self._pending_tools_manager.get_pending_list())
        except Exception:
            pending_tools = 0
        try:
            pending_evolutions = len(self._pending_evolutions_manager.get_all_pending())
        except Exception:
            pending_evolutions = 0
        return {"pending_tools": pending_tools, "pending_evolutions": pending_evolutions}

    def _collect_quality_summary(self) -> Dict[str, Any]:
        try:
            return self._quality_analyzer.get_summary(days=7)
        except Exception:
            return {"total_tools": 0, "avg_health_score": 0.0, "healthy_tools": 0, "monitor_tools": 0, "weak_tools": 0, "quarantine_tools": 0}

    def _evaluate_cycle_quality(
        self,
        *,
        gaps_count: int,
        auto_result: Dict[str, Any],
        loop_result: Dict[str, Any],
        pending_before: Dict[str, int],
        pending_after: Dict[str, int],
        quality_before: Dict[str, Any],
        quality_after: Dict[str, Any],
    ) -> Dict[str, Any]:
        new_pending_tools = max(0, pending_after["pending_tools"] - pending_before["pending_tools"])
        new_pending_evolutions = max(0, pending_after["pending_evolutions"] - pending_before["pending_evolutions"])
        preview_count = int(loop_result.get("preview_count", 0) or 0)
        processed = int(auto_result.get("processed", 0) or 0)
        failures = int(auto_result.get("failures", 0) or 0)
        avg_health_delta = float(quality_after.get("avg_health_score", 0.0) or 0.0) - float(
            quality_before.get("avg_health_score", 0.0) or 0.0
        )

        score = 0.0
        score += min(new_pending_tools, 1) * 0.4
        score += min(new_pending_evolutions, 1) * 0.35
        score += min(preview_count, 1) * 0.2
        score += min(processed, 1) * 0.1
        if avg_health_delta > 0:
            score += 0.1
        # Only penalise failures if nothing was produced — failures with output mean partial success
        if failures > 0 and (new_pending_tools + new_pending_evolutions + preview_count) == 0:
            score -= min(failures * 0.2, 0.4)
        score = max(0.0, min(1.0, score))

        actionable_outputs = new_pending_tools + new_pending_evolutions + preview_count
        # Idle (nothing to improve) is not low-value — only penalise when there were gaps but nothing resolved
        low_value = score < float(self.config["min_usefulness_score"]) and gaps_count > 0 and actionable_outputs == 0
        if low_value:
            self.consecutive_low_value_cycles += 1
        else:
            self.consecutive_low_value_cycles = 0

        should_pause = bool(self.config.get("pause_on_low_value")) and (
            self.consecutive_low_value_cycles >= int(self.config["max_consecutive_low_value_cycles"])
        )

        reason_parts = []
        if actionable_outputs == 0:
            reason_parts.append("no actionable outputs")
        if failures:
            reason_parts.append(f"{failures} auto-evolution failures")
        if gaps_count > 0 and actionable_outputs == 0:
            reason_parts.append("gaps remain unresolved")
        reason = ", ".join(reason_parts) or "cycle produced actionable outputs"

        return {
            "score": round(score, 3),
            "low_value": low_value,
            "should_pause": should_pause,
            "reason": reason,
            "new_pending_tools": new_pending_tools,
            "new_pending_evolutions": new_pending_evolutions,
            "preview_count": preview_count,
            "processed": processed,
            "failures": failures,
            "avg_health_delta": round(avg_health_delta, 3),
            "consecutive_low_value_cycles": self.consecutive_low_value_cycles,
        }

    def get_status(self):
        return {
            "running": self.running,
            "cycle_count": self.cycle_count,
            "consecutive_low_value_cycles": self.consecutive_low_value_cycles,
            "paused_reason": self.paused_reason,
            "config": self.config,
            "last_error": self.last_error,
            "last_cycle": self.last_cycle,
            "auto_evolution": self.auto_orchestrator.get_status(),
        }
