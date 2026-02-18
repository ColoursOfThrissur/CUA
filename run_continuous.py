#!/usr/bin/env python3
"""
Controlled Continuous Self-Improvement Loop
"""
import time
import json
from pathlib import Path
from core.loop_controller import LoopController
from core.config_manager import get_config

CONTROL_FILE = Path("data/continuous_control.json")

class ContinuousController:
    def __init__(self):
        self.config = get_config()
        self.controller = LoopController(self.config)
        self.iteration = 0
        self.total_improvements = 0
        self.failures = 0
        
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
                
                result = self.controller.run_loop(max_iterations=5)
                
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
