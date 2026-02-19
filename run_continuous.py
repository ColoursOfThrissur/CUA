#!/usr/bin/env python3
"""
Controlled Continuous Self-Improvement Loop
"""
import time
import json
import asyncio
from pathlib import Path
from core.config_manager import get_config
from tools.capability_registry import CapabilityRegistry
from tools.enhanced_filesystem_tool import FilesystemTool
from tools.http_tool import HTTPTool
from tools.json_tool import JSONTool
from tools.shell_tool import ShellTool
from planner.llm_client import LLMClient
from updater.orchestrator import UpdateOrchestrator
from core.improvement_loop import SelfImprovementLoop

CONTROL_FILE = Path("data/continuous_control.json")

class ContinuousController:
    def __init__(self):
        self.config = get_config()
        self.loop = self._build_loop()
        self.iteration = 0
        self.total_improvements = 0
        self.failures = 0

    def _build_loop(self):
        registry = CapabilityRegistry()
        registry.register_tool(FilesystemTool())
        registry.register_tool(HTTPTool())
        registry.register_tool(JSONTool())
        registry.register_tool(ShellTool())

        llm_client = LLMClient(registry=registry)
        orchestrator = UpdateOrchestrator(repo_path=".")
        return SelfImprovementLoop(
            llm_client=llm_client,
            orchestrator=orchestrator,
            max_iterations=self.config.improvement.max_iterations
        )

    async def _run_single_cycle(self, max_iterations: int, dry_run: bool):
        self.loop.controller.max_iterations = max_iterations
        self.loop.dry_run = dry_run
        self.loop.continuous_mode = False

        start_result = await self.loop.start_loop()
        if "error" in start_result:
            return {"status": "failed", "error": start_result["error"], "improvements_made": 0}

        # start_loop schedules work; wait until loop fully stops
        while self.loop.state.status.value in ("running", "stopping"):
            await asyncio.sleep(1)

        successes = sum(
            1 for item in self.loop.controller.iteration_history
            if item.get("result") == "success"
        )
        return {"status": "completed", "improvements_made": successes}
        
    def load_control(self):
        """Load control settings"""
        if CONTROL_FILE.exists():
            with open(CONTROL_FILE) as f:
                return json.load(f)
        return {"running": True, "paused": False, "max_cycles": None, "cycle_delay": 30}
    
    def save_status(self, status: str):
        """Save current status"""
        data = {
            "status": status,
            "iteration": self.iteration,
            "total_improvements": self.total_improvements,
            "failures": self.failures
        }
        Path("data").mkdir(exist_ok=True)
        with open("data/continuous_status.json", "w") as f:
            json.dump(data, f, indent=2)
    
    def run(self):
        print("=" * 60)
        print("CUA CONTROLLED CONTINUOUS IMPROVEMENT")
        print("=" * 60)
        print("Controls: Edit data/continuous_control.json")
        print("  - running: false (stop gracefully)")
        print("  - paused: true (pause)")
        print("  - max_cycles: N (stop after N cycles)")
        print("  - cycle_delay: seconds between cycles")
        print("\nPress Ctrl+C for immediate stop")
        print()
        
        try:
            while True:
                control = self.load_control()
                
                # Check stop condition
                if not control.get("running", True):
                    print("\n[STOPPED] Graceful shutdown requested")
                    break
                
                # Check max cycles
                if control.get("max_cycles") and self.iteration >= control["max_cycles"]:
                    print(f"\n[COMPLETED] Reached max cycles: {control['max_cycles']}")
                    break
                
                # Check pause
                if control.get("paused", False):
                    print("\r[PAUSED] Waiting...", end="", flush=True)
                    time.sleep(5)
                    continue
                
                self.iteration += 1
                print(f"\n[CYCLE {self.iteration}] Starting...")
                self.save_status("running")
                
                max_iterations = int(control.get("max_iterations", 5) or 5)
                dry_run = bool(control.get("dry_run", False))
                result = asyncio.run(self._run_single_cycle(max_iterations=max_iterations, dry_run=dry_run))
                
                if result.get("status") == "completed":
                    improvements = result.get('improvements_made', 0)
                    self.total_improvements += improvements
                    print(f"[CYCLE {self.iteration}] ✓ {improvements} improvements (total: {self.total_improvements})")
                else:
                    self.failures += 1
                    print(f"[CYCLE {self.iteration}] ✗ Failed (total failures: {self.failures})")
                    
                    # Stop after 3 consecutive failures
                    if self.failures >= 3:
                        print("\n[STOPPED] Too many failures")
                        break
                
                delay = control.get("cycle_delay", 30)
                print(f"Waiting {delay}s...")
                time.sleep(delay)
                
        except KeyboardInterrupt:
            print("\n\n[STOPPED] Interrupted by user")
        finally:
            self.save_status("stopped")
            print(f"\nFinal Stats:")
            print(f"  Cycles: {self.iteration}")
            print(f"  Improvements: {self.total_improvements}")
            print(f"  Failures: {self.failures}")

if __name__ == "__main__":
    # Initialize control file
    CONTROL_FILE.parent.mkdir(exist_ok=True)
    if not CONTROL_FILE.exists():
        with open(CONTROL_FILE, "w") as f:
            json.dump({"running": True, "paused": False, "max_cycles": None, "cycle_delay": 30}, f, indent=2)
    
    ContinuousController().run()
