"""
SystemHealthTool — AI-runtime-aware health monitoring for CUA.

5 layers:
  1. System      — CPU, RAM, disk, GPU (psutil)
  2. LLM Runtime — Ollama process, model loaded, p50/p95 latency, token burn rate
  3. Agent       — tool success rates, circuit breakers, loop detection, planning trend
  4. CUA         — pending queues, DB size, WAL pressure, last autonomy cycle
  5. Advisor     — LLM synthesizes all layers into bottlenecks + specific actions
"""
import json
import os
import time
from datetime import datetime, timezone
from shared.config.branding import get_platform_name
from tools.tool_interface import BaseTool
from tools.tool_result import ToolResult, ResultStatus
from tools.tool_capability import ToolCapability, Parameter, ParameterType, SafetyLevel


class SystemHealthTool(BaseTool):
    """AI-runtime-aware health monitoring — system + LLM + agent + CUA internals."""

    def __init__(self, orchestrator=None):
        self.description = "System health monitoring: CPU/RAM/disk, Ollama runtime, agent behavior, platform internals, and LLM advisor diagnosis."
        self.services = orchestrator.get_services(self.__class__.__name__) if orchestrator else None
        super().__init__()

    def register_capabilities(self):
        self.add_capability(ToolCapability(
            name="get_system_metrics",
            description="CPU, RAM, disk usage and top processes by memory. Includes GPU if nvidia-smi available.",
            parameters=[],
            returns="dict", safety_level=SafetyLevel.LOW, examples=[], dependencies=["psutil"]
        ), self._handle_get_system_metrics)

        self.add_capability(ToolCapability(
            name="get_llm_runtime",
            description="Ollama process stats, model loaded, p50/p95/p99 LLM call latency from cua.db, token burn rate per session.",
            parameters=[
                Parameter("hours", ParameterType.INTEGER, "Hours of history to analyse. Default: 1", required=False, default=1),
            ],
            returns="dict", safety_level=SafetyLevel.LOW, examples=[], dependencies=["psutil"]
        ), self._handle_get_llm_runtime)

        self.add_capability(ToolCapability(
            name="get_agent_behavior",
            description="Tool call success rates, circuit breaker states, loop detection (repeated same-params calls), planning latency trend.",
            parameters=[
                Parameter("hours", ParameterType.INTEGER, "Hours of history to analyse. Default: 1", required=False, default=1),
            ],
            returns="dict", safety_level=SafetyLevel.LOW, examples=[], dependencies=[]
        ), self._handle_get_agent_behavior)

        self.add_capability(ToolCapability(
            name="get_cua_internals",
            description="Pending queues depth, cua.db size and WAL pressure, last autonomy cycle outcome, evolution backlog.",
            parameters=[],
            returns="dict", safety_level=SafetyLevel.LOW, examples=[], dependencies=[]
        ), self._handle_get_cua_internals)

        self.add_capability(ToolCapability(
            name="get_health_report",
            description="Full health report: runs all 4 layers then LLM advisor identifies bottlenecks and gives specific actionable fixes.",
            parameters=[
                Parameter("hours", ParameterType.INTEGER, "Hours of history to analyse. Default: 1", required=False, default=1),
            ],
            returns="dict", safety_level=SafetyLevel.LOW, examples=[], dependencies=["psutil"]
        ), self._handle_get_health_report)

    def execute(self, operation: str, **kwargs) -> ToolResult:
        return self.execute_capability(operation, **kwargs)

    # ── Layer 1: System ───────────────────────────────────────────────────────

    def _handle_get_system_metrics(self, **kwargs) -> dict:
        try:
            import psutil
        except ImportError:
            return {"success": False, "error": "psutil not installed. Run: pip install psutil"}

        try:
            cpu_pct = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage(".")

            # Top 5 processes by memory
            procs = []
            for p in sorted(psutil.process_iter(["pid", "name", "memory_info", "cpu_percent"]),
                            key=lambda x: x.info["memory_info"].rss if x.info["memory_info"] else 0,
                            reverse=True)[:5]:
                try:
                    procs.append({
                        "pid": p.info["pid"],
                        "name": p.info["name"],
                        "memory_mb": round(p.info["memory_info"].rss / 1024 / 1024, 1),
                        "cpu_pct": p.info["cpu_percent"],
                    })
                except Exception:
                    pass

            # GPU via nvidia-smi (optional)
            gpu = self._get_gpu_stats()

            return {
                "success": True,
                "cpu_percent": cpu_pct,
                "cpu_count": psutil.cpu_count(),
                "memory": {
                    "total_gb": round(mem.total / 1024**3, 2),
                    "used_gb": round(mem.used / 1024**3, 2),
                    "free_gb": round(mem.available / 1024**3, 2),
                    "percent": mem.percent,
                },
                "disk": {
                    "total_gb": round(disk.total / 1024**3, 2),
                    "used_gb": round(disk.used / 1024**3, 2),
                    "free_gb": round(disk.free / 1024**3, 2),
                    "percent": disk.percent,
                },
                "top_processes": procs,
                "gpu": gpu,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_gpu_stats(self) -> dict:
        try:
            import subprocess
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu",
                 "--format=csv,noheader,nounits"],
                timeout=3, stderr=subprocess.DEVNULL
            ).decode().strip()
            parts = [p.strip() for p in out.split(",")]
            if len(parts) >= 4:
                return {
                    "name": parts[0],
                    "memory_used_mb": int(parts[1]),
                    "memory_total_mb": int(parts[2]),
                    "utilization_pct": int(parts[3]),
                }
        except Exception:
            pass
        return None

    # ── Layer 2: LLM Runtime ─────────────────────────────────────────────────

    def _handle_get_llm_runtime(self, **kwargs) -> dict:
        hours = int(kwargs.get("hours") or 1)
        try:
            import psutil
        except ImportError:
            return {"success": False, "error": "psutil not installed"}

        result = {"success": True, "hours_analysed": hours}

        # Ollama process
        ollama_proc = None
        for p in psutil.process_iter(["pid", "name", "memory_info", "cpu_percent", "status"]):
            try:
                if "ollama" in p.info["name"].lower():
                    ollama_proc = p
                    break
            except Exception:
                pass

        if ollama_proc:
            try:
                result["ollama"] = {
                    "running": True,
                    "pid": ollama_proc.pid,
                    "memory_gb": round(ollama_proc.info["memory_info"].rss / 1024**3, 2),
                    "cpu_pct": ollama_proc.info["cpu_percent"],
                    "status": ollama_proc.info["status"],
                }
            except Exception:
                result["ollama"] = {"running": True, "error": "could not read stats"}
        else:
            result["ollama"] = {"running": False, "warning": "Ollama process not found"}

        # LLM call latency from cua.db logs
        try:
            import sqlite3
            conn = sqlite3.connect("data/cua.db")
            cutoff = datetime.now(timezone.utc).timestamp() - hours * 3600

            # Execution times for LLM-heavy operations (planning, evolution)
            rows = conn.execute("""
                SELECT execution_time_ms FROM executions
                WHERE timestamp > ? AND execution_time_ms IS NOT NULL
                ORDER BY execution_time_ms
            """, (cutoff,)).fetchall()
            conn.close()

            times = sorted([r[0] for r in rows if r[0] and r[0] > 0])
            if times:
                n = len(times)
                result["latency"] = {
                    "sample_count": n,
                    "p50_ms": round(times[int(n * 0.50)], 1),
                    "p95_ms": round(times[int(n * 0.95)], 1),
                    "p99_ms": round(times[min(int(n * 0.99), n - 1)], 1),
                    "avg_ms": round(sum(times) / n, 1),
                    "max_ms": round(times[-1], 1),
                }
            else:
                result["latency"] = {"sample_count": 0, "note": "no executions in window"}

            # Token burn rate estimate (avg 4 chars per token)
            conn2 = sqlite3.connect("data/cua.db")
            log_rows = conn2.execute("""
                SELECT message FROM logs
                WHERE timestamp > ? AND service = 'llm_client'
                AND message LIKE '%temp=%'
            """, (datetime.fromtimestamp(cutoff).isoformat(),)).fetchall()
            conn2.close()
            result["llm_calls"] = {
                "count_in_window": len(log_rows),
                "rate_per_hour": round(len(log_rows) / max(hours, 1), 1),
            }

        except Exception as e:
            result["latency"] = {"error": str(e)}

        return result

    # ── Layer 3: Agent Behavior ───────────────────────────────────────────────

    def _handle_get_agent_behavior(self, **kwargs) -> dict:
        hours = int(kwargs.get("hours") or 1)
        try:
            import sqlite3
            conn = sqlite3.connect("data/cua.db")
            cutoff = datetime.now(timezone.utc).timestamp() - hours * 3600

            rows = conn.execute("""
                SELECT tool_name, operation, success, execution_time_ms, parameters, timestamp
                FROM executions WHERE timestamp > ?
                ORDER BY timestamp DESC
            """, (cutoff,)).fetchall()
            conn.close()
        except Exception as e:
            return {"success": False, "error": str(e)}

        if not rows:
            return {"success": True, "hours_analysed": hours, "note": "no executions in window"}

        # Per-tool success rates
        tool_stats = {}
        for tool, op, success, latency, params, ts in rows:
            key = f"{tool}.{op}"
            if key not in tool_stats:
                tool_stats[key] = {"total": 0, "success": 0, "latencies": []}
            tool_stats[key]["total"] += 1
            if success:
                tool_stats[key]["success"] += 1
            if latency:
                tool_stats[key]["latencies"].append(latency)

        tool_summary = {}
        for key, s in tool_stats.items():
            lats = sorted(s["latencies"])
            tool_summary[key] = {
                "total": s["total"],
                "success_rate": round(s["success"] / s["total"], 2),
                "avg_ms": round(sum(lats) / len(lats), 1) if lats else None,
            }

        # Loop detection — same tool+operation+params called 3+ times
        from collections import Counter
        call_fingerprints = []
        for tool, op, success, latency, params, ts in rows:
            # Normalize params to detect repeated identical calls
            try:
                p = json.loads(params) if params else {}
                # Only use top-level keys for fingerprint, not full values
                fp = f"{tool}.{op}:{sorted(p.keys())}"
            except Exception:
                fp = f"{tool}.{op}"
            call_fingerprints.append(fp)

        loop_candidates = [
            {"call": fp, "count": count}
            for fp, count in Counter(call_fingerprints).items()
            if count >= 3
        ]

        # Circuit breaker states from circuit_breaker module
        cb_states = {}
        try:
            from infrastructure.failure_handling.circuit_breaker import get_circuit_breaker
            cb = get_circuit_breaker()
            for tool_name, circuit in cb.circuits.items():
                state = circuit.state.value
                if state != "closed":
                    cb_states[tool_name] = {
                        "state": state,
                        "failure_rate": round(circuit.failure_rate(), 2),
                        "window_size": circuit.total_calls(),
                    }
        except Exception:
            pass

        # Planning latency trend — are plans getting slower?
        planning_times = [
            r[3] for r in rows
            if r[0] in ("TaskPlanner", "task_planner") and r[3]
        ]
        planning_trend = None
        if len(planning_times) >= 4:
            mid = len(planning_times) // 2
            first_half_avg = sum(planning_times[:mid]) / mid
            second_half_avg = sum(planning_times[mid:]) / (len(planning_times) - mid)
            delta_pct = round((second_half_avg - first_half_avg) / max(first_half_avg, 1) * 100, 1)
            planning_trend = {
                "first_half_avg_ms": round(first_half_avg, 1),
                "second_half_avg_ms": round(second_half_avg, 1),
                "trend_pct": delta_pct,
                "direction": "degrading" if delta_pct > 10 else ("improving" if delta_pct < -10 else "stable"),
            }

        return {
            "success": True,
            "hours_analysed": hours,
            "total_calls": len(rows),
            "tool_success_rates": tool_summary,
            "open_circuit_breakers": cb_states,
            "loop_detection": loop_candidates,
            "planning_trend": planning_trend,
        }

    # ── Layer 4: CUA Internals ────────────────────────────────────────────────

    def _handle_get_cua_internals(self, **kwargs) -> dict:
        result = {"success": True}

        # DB sizes
        db_files = {
            "cua.db": "data/cua.db",
            "conversations.db": "data/conversations.db",
            "strategic_memory.json": "data/strategic_memory.json",
        }
        db_sizes = {}
        for name, path in db_files.items():
            try:
                size = os.path.getsize(path)
                db_sizes[name] = {"size_mb": round(size / 1024 / 1024, 2)}
                # WAL file pressure
                wal = path + "-wal"
                if os.path.exists(wal):
                    wal_size = os.path.getsize(wal)
                    db_sizes[name]["wal_mb"] = round(wal_size / 1024 / 1024, 2)
                    if wal_size > 10 * 1024 * 1024:
                        db_sizes[name]["wal_warning"] = "WAL > 10MB — checkpoint may be needed"
            except Exception:
                pass
        result["databases"] = db_sizes

        # Pending queues
        queues = {}
        queue_files = {
            "pending_evolutions": "data/pending_evolutions.json",
            "pending_tools": "data/pending_tools.json",
            "pending_services": "data/pending_services.json",
            "capability_gaps": "data/capability_gaps.json",
        }
        for name, path in queue_files.items():
            try:
                data = json.loads(open(path).read())
                count = len(data) if isinstance(data, list) else len(data.get("items", data.get("pending", [])))
                queues[name] = count
            except Exception:
                queues[name] = 0
        result["pending_queues"] = queues

        # Last autonomy cycle
        try:
            import sqlite3
            conn = sqlite3.connect("data/cua.db")
            row = conn.execute("""
                SELECT hour_timestamp, tools_analyzed, evolutions_triggered, evolutions_approved
                FROM auto_evolution_metrics ORDER BY id DESC LIMIT 1
            """).fetchone()
            conn.close()
            if row:
                result["last_autonomy_cycle"] = {
                    "timestamp": row[0],
                    "tools_analyzed": row[1],
                    "evolutions_triggered": row[2],
                    "evolutions_approved": row[3],
                }
        except Exception:
            pass

        # Open circuit breakers count
        try:
            from infrastructure.failure_handling.circuit_breaker import get_circuit_breaker
            open_count = len(get_circuit_breaker().get_all_open_circuits())
            result["open_circuit_breakers"] = open_count
        except Exception:
            pass

        return result

    # ── Layer 5: LLM Advisor ─────────────────────────────────────────────────

    def _handle_get_health_report(self, **kwargs) -> dict:
        hours = int(kwargs.get("hours") or 1)

        system = self._handle_get_system_metrics()
        llm_rt = self._handle_get_llm_runtime(hours=hours)
        agent = self._handle_get_agent_behavior(hours=hours)
        internals = self._handle_get_cua_internals()

        # Build structured context for LLM
        context_parts = [f"TIMESTAMP: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"]

        if system.get("success"):
            context_parts.append(
                f"SYSTEM:\n"
                f"  CPU: {system['cpu_percent']}%\n"
                f"  RAM: {system['memory']['used_gb']}GB used / {system['memory']['total_gb']}GB total ({system['memory']['percent']}%)\n"
                f"  Disk: {system['disk']['free_gb']}GB free ({system['disk']['percent']}% used)\n"
                f"  Top process: {system['top_processes'][0]['name']} {system['top_processes'][0]['memory_mb']}MB" if system.get('top_processes') else ""
            )
            if system.get("gpu"):
                g = system["gpu"]
                context_parts.append(f"  GPU: {g['name']} {g['memory_used_mb']}MB/{g['memory_total_mb']}MB ({g['utilization_pct']}% util)")

        if llm_rt.get("success"):
            ollama = llm_rt.get("ollama", {})
            context_parts.append(
                f"LLM RUNTIME:\n"
                f"  Ollama: {'running' if ollama.get('running') else 'NOT RUNNING'}"
                + (f" — {ollama.get('memory_gb')}GB RAM, {ollama.get('cpu_pct')}% CPU" if ollama.get('memory_gb') else "")
            )
            if llm_rt.get("latency", {}).get("sample_count", 0) > 0:
                lat = llm_rt["latency"]
                context_parts.append(
                    f"  Latency: p50={lat['p50_ms']}ms p95={lat['p95_ms']}ms p99={lat['p99_ms']}ms (n={lat['sample_count']})"
                )
            if llm_rt.get("llm_calls"):
                context_parts.append(f"  LLM calls: {llm_rt['llm_calls']['count_in_window']} in {hours}h ({llm_rt['llm_calls']['rate_per_hour']}/hr)")

        if agent.get("success"):
            failing = {k: v for k, v in agent.get("tool_success_rates", {}).items() if v["success_rate"] < 0.7}
            if failing:
                context_parts.append(f"FAILING TOOLS (success rate < 70%):\n" + "\n".join(f"  {k}: {v['success_rate']:.0%}" for k, v in failing.items()))
            if agent.get("open_circuit_breakers"):
                context_parts.append(f"OPEN CIRCUIT BREAKERS: {list(agent['open_circuit_breakers'].keys())}")
            if agent.get("loop_detection"):
                context_parts.append(f"LOOP DETECTION — repeated calls:\n" + "\n".join(f"  {l['call']}: {l['count']}x" for l in agent["loop_detection"]))
            if agent.get("planning_trend") and agent["planning_trend"]["direction"] != "stable":
                pt = agent["planning_trend"]
                context_parts.append(f"PLANNING TREND: {pt['direction']} ({pt['trend_pct']:+.1f}%) avg={pt['second_half_avg_ms']}ms")

        if internals.get("success"):
            queues = internals.get("pending_queues", {})
            nonempty = {k: v for k, v in queues.items() if v > 0}
            if nonempty:
                context_parts.append(f"PENDING QUEUES: {nonempty}")
            for db, info in internals.get("databases", {}).items():
                if info.get("wal_warning"):
                    context_parts.append(f"DB WARNING: {db} — {info['wal_warning']}")

        prompt = (
            f"You are a DevOps engineer and AI systems expert diagnosing {get_platform_name()}.\n"
            "Analyse the health data below and give a concise diagnosis.\n\n"
            + "\n\n".join(context_parts)
            + "\n\nReply with JSON:\n"
            '{"status": "healthy|degraded|critical", '
            '"summary": "1-2 sentence overview", '
            '"bottlenecks": ["specific issue 1", ...], '
            '"actions": ["specific fix 1 e.g. set max_workers=1 in config.yaml", ...], '
            '"warnings": ["non-critical warning 1", ...]}'
        )

        try:
            raw = self.services.llm.generate(prompt, temperature=0.2, max_tokens=600)
            import re
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            parsed = json.loads(match.group()) if match else {}
        except Exception as e:
            parsed = {"error": str(e)}

        return {
            "success": True,
            "status": parsed.get("status", "unknown"),
            "summary": parsed.get("summary", ""),
            "bottlenecks": parsed.get("bottlenecks", []),
            "actions": parsed.get("actions", []),
            "warnings": parsed.get("warnings", []),
            "layers": {
                "system": {k: v for k, v in system.items() if k != "success"},
                "llm_runtime": {k: v for k, v in llm_rt.items() if k != "success"},
                "agent_behavior": {k: v for k, v in agent.items() if k != "success"},
                "cua_internals": {k: v for k, v in internals.items() if k != "success"},
            },
        }
