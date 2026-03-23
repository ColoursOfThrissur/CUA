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
        self.config = {
            "interval_seconds": 6 * 60 * 60,
            "improvement_iterations_per_cycle": 3,
            "max_evolutions_per_cycle": 2,
            "dry_run": False,
            "min_usefulness_score": 0.35,
            "max_consecutive_low_value_cycles": 2,
            "pause_on_low_value": True,
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
            elapsed = time.time() - started
            sleep_for = max(5, self.config["interval_seconds"] - elapsed)
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
        pending_before = self._collect_pending_counts()
        quality_before = self._collect_quality_summary()

        broadcast_trace_sync("auto", "Running auto-evolution pass", "in_progress", {"stage": "auto_evolution"})
        auto_result = await self.auto_orchestrator.run_cycle(
            max_items=self.config["max_evolutions_per_cycle"]
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
            pending_tools = len(PendingToolsManager().get_pending_list())
        except Exception:
            pending_tools = 0
        try:
            pending_evolutions = len(PendingEvolutionsManager().get_all_pending())
        except Exception:
            pending_evolutions = 0
        return {
            "pending_tools": pending_tools,
            "pending_evolutions": pending_evolutions,
        }

    def _collect_quality_summary(self) -> Dict[str, Any]:
        try:
            return ToolQualityAnalyzer().get_summary(days=7)
        except Exception:
            return {
                "total_tools": 0,
                "avg_health_score": 0.0,
                "healthy_tools": 0,
                "monitor_tools": 0,
                "weak_tools": 0,
                "quarantine_tools": 0,
            }

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
        score -= min(failures * 0.2, 0.4)
        score = max(0.0, min(1.0, score))

        actionable_outputs = new_pending_tools + new_pending_evolutions + preview_count
        low_value = score < float(self.config["min_usefulness_score"]) or (
            gaps_count > 0 and actionable_outputs == 0
        )
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
