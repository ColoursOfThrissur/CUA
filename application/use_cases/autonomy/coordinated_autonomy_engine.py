"""Coordinated unattended autonomy engine for scheduled self-improvement cycles."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from application.use_cases.autonomy.baseline_health_checker import BaselineHealthChecker
from domain.services.gap_tracker import GapTracker
from application.managers.pending_evolutions_manager import PendingEvolutionsManager
from application.managers.pending_tools_manager import PendingToolsManager
from domain.services.tool_quality_analyzer import ToolQualityAnalyzer
from infrastructure.logging.tool_execution_logger import get_execution_logger
from shared.utils.trace_bridge import broadcast_trace_sync


class CoordinatedAutonomyEngine:
    """Coordinates health checks, gap review, auto-evolution, and bounded improvement loops."""

    def __init__(
        self,
        improvement_loop,
        llm_client,
        registry,
        auto_orchestrator=None,
    ):
        from application.use_cases.autonomy.auto_evolution_orchestrator import AutoEvolutionOrchestrator

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
        self._quality_analyzer = ToolQualityAnalyzer(get_execution_logger())
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
        from domain.services.capability_resolver import CapabilityResolver
        from domain.services.gap_detector import CapabilityGap as _CG
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

        # Tool creation phase — always runs after evolution every cycle.
        # Pending evolutions waiting for approval are NOT a blocker — that's
        # the user's job. Creation is proactive: it analyses what the system
        # is missing, not what users have complained about.
        broadcast_trace_sync("auto", "Running tool creation phase", "in_progress", {"stage": "tool_creation"})
        creation_result = await self._run_creation_phase()
        if creation_result.get("queued"):
            broadcast_trace_sync(
                "auto",
                f"Tool creation: {creation_result['queued']} tool(s) queued",
                "in_progress",
                {"stage": "tool_creation", "queued": creation_result["queued"]},
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
            from infrastructure.persistence.sqlite.cua_database import get_conn
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
        """Proactively identify and queue tool creation every cycle.

        Two signal sources, merged and deduplicated:
        1. GapTracker — user-triggered failures that surfaced a missing capability
        2. Proactive LLM analysis — LLM reasons about the full system (skills,
           existing tools, covered capabilities) and identifies what's missing
           without waiting for a user to hit the gap first.

        max_new_tools_per_scan caps how many tools are created per cycle.
        Pending approvals are NOT a blocker — creation is independent.
        """
        try:
            await self.auto_orchestrator.ensure_initialized()
            max_new = int(self.auto_orchestrator.config.get("max_new_tools_per_scan", 1))

            # Build covered capabilities set
            covered_caps: set = set()
            if self.registry:
                try:
                    for tool in getattr(self.registry, "tools", []):
                        for cap_name in (tool.get_capabilities() or {}):
                            covered_caps.add(cap_name.lower())
                        covered_caps.add(tool.__class__.__name__.lower().replace("tool", ""))
                except Exception:
                    pass

            # --- Signal 1: user-triggered gaps from GapTracker ---
            from domain.services.gap_tracker import GapTracker
            tracker = GapTracker()
            actionable = tracker.get_actionable_gaps()
            reactive_gaps = [
                {"capability": g.capability, "reason": g.reasons[0] if g.reasons else "",
                 "confidence": g.confidence_avg, "source": "gap_tracker",
                 "preferred_name": getattr(g, "target_tool", None)}
                for g in actionable if g.suggested_action == "create_tool"
            ]

            # --- Signal 2: proactive LLM system analysis ---
            proactive_gaps = await self._proactive_gap_analysis(covered_caps)

            # Merge, deduplicate by capability key, reactive takes priority
            seen_caps: set = set()
            all_gaps = []
            for g in reactive_gaps + proactive_gaps:
                key = (g["capability"] or "").lower().replace(":", "_").replace(" ", "_")
                if key and key not in seen_caps and key not in covered_caps:
                    seen_caps.add(key)
                    all_gaps.append(g)

            if not all_gaps:
                return {"skipped": True, "reason": "No capability gaps identified (reactive=0, proactive=0)", "queued": 0}

            from application.use_cases.evolution.evolution_queue import QueuedEvolution
            queued = 0
            for gap in all_gaps:
                if queued >= max_new:
                    break
                cap = gap["capability"]
                tool_name = f"CREATE::{cap}"
                if self.auto_orchestrator.queue.is_queued(tool_name):
                    continue

                preferred_name = (
                    gap.get("preferred_name")
                    or "".join(p.capitalize() for p in str(cap).split("_")) + "Tool"
                )
                evolution = QueuedEvolution(
                    tool_name=tool_name,
                    urgency_score=75.0 if gap["source"] == "gap_tracker" else 60.0,
                    impact_score=65.0,
                    feasibility_score=65.0,
                    timing_score=75.0,
                    reason=f"[{gap['source']}] Missing capability: {cap} — {gap['reason'][:80]}",
                    metadata={
                        "kind": "create_tool",
                        "gap_capability": cap,
                        "gap_description": f"Add capability: {cap}. Reason: {gap['reason']}",
                        "preferred_name": preferred_name,
                        "source": gap["source"],
                    },
                )
                self.auto_orchestrator.queue.add(evolution)
                if gap["source"] == "gap_tracker":
                    tracker.mark_resolved(cap, "create_tool")
                queued += 1
                broadcast_trace_sync(
                    "auto",
                    f"Queued tool creation: {cap} [{gap['source']}]",
                    "in_progress",
                    {"stage": "tool_creation", "capability": cap, "source": gap["source"]},
                )

            if queued > 0:
                await self.auto_orchestrator.run_cycle(max_items=queued, rescan=False)

            return {
                "queued": queued,
                "reactive_gaps": len(reactive_gaps),
                "proactive_gaps": len(proactive_gaps),
                "total_candidates": len(all_gaps),
            }

        except Exception as e:
            return {"skipped": True, "reason": str(e), "queued": 0}

    async def _proactive_gap_analysis(self, covered_caps: set) -> list:
        """LLM analyses the full system every cycle to find missing capabilities.

        Looks at: loaded tools, skill definitions, covered capabilities.
        Returns gaps the system is missing regardless of user activity.
        Capped at 2 per cycle to avoid flooding the creation queue.
        """
        try:
            import json as _json
            from pathlib import Path
            from shared.config.model_manager import get_model_manager
            
            # Switch to qwen3.5 for autonomy scanning
            model_manager = get_model_manager(self.llm_client)
            model_manager.switch_to("autonomy")

            # Build system snapshot
            skills_snapshot = []
            for skill_dir in sorted(Path("skills").iterdir()):
                skill_json = skill_dir / "skill.json"
                if not skill_json.exists():
                    continue
                try:
                    sd = _json.loads(skill_json.read_text())
                    skills_snapshot.append({
                        "name": sd.get("name", skill_dir.name),
                        "description": sd.get("description", ""),
                        "preferred_tools": sd.get("preferred_tools", []),
                    })
                except Exception:
                    pass

            existing_tools = [
                f.stem for base in [Path("tools"), Path("tools/experimental")]
                if base.exists()
                for f in base.glob("*.py")
                if not f.name.startswith("__")
            ]

            prompt = (
                "You are analysing a local autonomous agent platform to find missing tool capabilities.\n"
                "This platform plans tasks, routes via skills, calls tools, creates/evolves tools.\n"
                "Desktop automation is one subsystem, not the whole product.\n\n"
                f"SKILLS: {', '.join(s['name'] for s in skills_snapshot)}\n"
                f"SKILL DESCRIPTIONS: {'; '.join(s['description'] for s in skills_snapshot if s['description'])}\n"
                f"EXISTING TOOLS: {', '.join(existing_tools)}\n"
                f"COVERED CAPABILITIES (sample): {', '.join(sorted(covered_caps)[:40])}\n\n"
                "Identify up to 2 tool capabilities that are CLEARLY missing for a general-purpose autonomous agent.\n"
                "Think about: scheduling, notifications, email, calendar, code execution, file watching, "
                "image processing, PDF handling, API key management, caching, rate limiting, "
                "data validation, report generation, template rendering.\n"
                "Pick the 2 most impactful gaps that no existing tool covers.\n\n"
                "/no_think\n\n"
                "Return JSON array (max 2 items):\n"
                '[{"capability": "snake_case_name", "confidence": 0.0-1.0, '
                '"reason": "one sentence why this is needed", '
                '"suggested_tool_name": "ToolNameTool"}]\n'
                "Confidence >= 0.6 is sufficient. Return [] only if the system is truly complete."
            )

            raw = await asyncio.to_thread(
                self.llm_client._call_llm, prompt, 0.1, 600, True
            )
            data = _json.loads(raw) if isinstance(raw, str) else raw
            # LLM sometimes returns a single dict instead of a list
            if isinstance(data, dict):
                data = [data]
            if not isinstance(data, list):
                return []

            results = []
            for item in data:
                cap = (item.get("capability") or "").strip().lower().replace(" ", "_")
                conf = float(item.get("confidence", 0.0))
                reason = (item.get("reason") or "").strip()
                preferred = (item.get("suggested_tool_name") or "").strip()
                if not cap or conf < 0.6:
                    continue
                cap_key = cap.replace(":", "_")
                if cap_key in covered_caps:
                    continue
                results.append({
                    "capability": cap,
                    "confidence": conf,
                    "reason": reason,
                    "source": "proactive_llm",
                    "preferred_name": preferred or None,
                })

            broadcast_trace_sync(
                "auto",
                f"Proactive gap analysis: {len(results)} new capability gap(s) identified",
                "in_progress",
                {"stage": "proactive_analysis", "gaps": [r["capability"] for r in results]},
            )
            return results

        except Exception as e:
            broadcast_trace_sync("auto", f"Proactive gap analysis failed: {e}", "in_progress",
                                 {"stage": "proactive_analysis"})
            return []

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
