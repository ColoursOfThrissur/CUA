#!/usr/bin/env python3
"""
Control script for continuous improvement loop
"""
import json
from pathlib import Path

CONTROL_FILE = Path("data/continuous_control.json")

def load():
    if CONTROL_FILE.exists():
        with open(CONTROL_FILE) as f:
            return json.load(f)
    return {}

def save(data):
    CONTROL_FILE.parent.mkdir(exist_ok=True)
    with open(CONTROL_FILE, "w") as f:
        json.dump(data, f, indent=2)

def status():
    """Show current status"""
    status_file = Path("data/continuous_status.json")
    if status_file.exists():
        with open(status_file) as f:
            data = json.load(f)
            print(f"Status: {data['status']}")
            print(f"Cycles: {data['iteration']}")
            print(f"Improvements: {data['total_improvements']}")
            print(f"Failures: {data['failures']}")
    else:
        print("Not running")

def pause():
    """Pause the loop"""
    data = load()
    data["paused"] = True
    save(data)
    print("Loop paused")

def resume():
    """Resume the loop"""
    data = load()
    data["paused"] = False
    save(data)
    print("Loop resumed")

def stop():
    """Stop the loop gracefully"""
    data = load()
    data["running"] = False
    save(data)
    print("Stop requested (will finish current cycle)")

def set_max_cycles(n):
    """Set maximum cycles"""
    data = load()
    data["max_cycles"] = int(n) if n else None
    save(data)
    print(f"Max cycles: {data['max_cycles']}")

def set_delay(seconds):
    """Set delay between cycles"""
    data = load()
    data["cycle_delay"] = int(seconds)
    save(data)
    print(f"Cycle delay: {seconds}s")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python control_loop.py [command]")
        print("Commands:")
        print("  status          - Show current status")
        print("  pause           - Pause loop")
        print("  resume          - Resume loop")
        print("  stop            - Stop loop gracefully")
        print("  max_cycles N    - Set max cycles (or 'none')")
        print("  delay N         - Set delay in seconds")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "status":
        status()
    elif cmd == "pause":
        pause()
    elif cmd == "resume":
        resume()
    elif cmd == "stop":
        stop()
    elif cmd == "max_cycles":
        set_max_cycles(sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "none" else None)
    elif cmd == "delay":
        set_delay(sys.argv[2])
    else:
        print(f"Unknown command: {cmd}")
