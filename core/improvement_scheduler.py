"""
Improvement Scheduler - Run self-improvement on schedule
"""
import asyncio
import threading
from datetime import datetime, time as dt_time
from typing import Dict, List, Optional, Callable
import json
from pathlib import Path

class Schedule:
    def __init__(self, schedule_id: str, cron: str, enabled: bool = True, 
                 max_iterations: int = 5, dry_run: bool = False):
        self.schedule_id = schedule_id
        self.cron = cron  # Simple format: "daily:02:00" or "hourly" or "weekly:monday:03:00"
        self.enabled = enabled
        self.max_iterations = max_iterations
        self.dry_run = dry_run
        self.last_run = None
        self.next_run = None

class ImprovementScheduler:
    def __init__(self, config_path: str = "data/schedules.json"):
        self.config_path = Path(config_path)
        self.config_path.parent.mkdir(exist_ok=True)
        self.schedules: Dict[str, Schedule] = {}
        self.running = False
        self.thread = None
        self.callback: Optional[Callable] = None
        self._load_schedules()
    
    def _load_schedules(self):
        """Load schedules from config file"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    data = json.load(f)
                    for sched_data in data.get('schedules', []):
                        sched = Schedule(**sched_data)
                        self.schedules[sched.schedule_id] = sched
            except Exception:
                pass
    
    def _save_schedules(self):
        """Save schedules to config file"""
        data = {
            'schedules': [
                {
                    'schedule_id': s.schedule_id,
                    'cron': s.cron,
                    'enabled': s.enabled,
                    'max_iterations': s.max_iterations,
                    'dry_run': s.dry_run
                }
                for s in self.schedules.values()
            ]
        }
        with open(self.config_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def add_schedule(self, schedule_id: str, cron: str, max_iterations: int = 5, 
                     dry_run: bool = False) -> Schedule:
        """Add new schedule"""
        schedule = Schedule(schedule_id, cron, True, max_iterations, dry_run)
        self.schedules[schedule_id] = schedule
        self._save_schedules()
        return schedule
    
    def remove_schedule(self, schedule_id: str) -> bool:
        """Remove schedule"""
        if schedule_id in self.schedules:
            del self.schedules[schedule_id]
            self._save_schedules()
            return True
        return False
    
    def enable_schedule(self, schedule_id: str, enabled: bool = True) -> bool:
        """Enable/disable schedule"""
        if schedule_id in self.schedules:
            self.schedules[schedule_id].enabled = enabled
            self._save_schedules()
            return True
        return False
    
    def get_schedules(self) -> List[Dict]:
        """Get all schedules"""
        return [
            {
                'schedule_id': s.schedule_id,
                'cron': s.cron,
                'enabled': s.enabled,
                'max_iterations': s.max_iterations,
                'dry_run': s.dry_run,
                'last_run': s.last_run,
                'next_run': s.next_run
            }
            for s in self.schedules.values()
        ]
    
    def set_callback(self, callback: Callable):
        """Set callback function to trigger improvement loop"""
        self.callback = callback
    
    def start(self):
        """Start scheduler thread"""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._run_scheduler, daemon=True)
            self.thread.start()
    
    def stop(self):
        """Stop scheduler thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
    
    def _run_scheduler(self):
        """Main scheduler loop"""
        while self.running:
            now = datetime.now()
            
            for schedule in self.schedules.values():
                if not schedule.enabled:
                    continue
                
                if self._should_run(schedule, now):
                    schedule.last_run = now.isoformat()
                    
                    # Trigger callback
                    if self.callback:
                        try:
                            self.callback(schedule.max_iterations, schedule.dry_run)
                        except Exception:
                            pass
            
            # Check every minute
            threading.Event().wait(60)
    
    def _should_run(self, schedule: Schedule, now: datetime) -> bool:
        """Check if schedule should run now"""
        if schedule.last_run:
            last = datetime.fromisoformat(schedule.last_run)
            # Don't run if ran in last hour
            if (now - last).total_seconds() < 3600:
                return False
        
        cron = schedule.cron.lower()
        
        if cron == "hourly":
            return now.minute == 0
        
        if cron.startswith("daily:"):
            target_time = cron.split(":")[1:]
            target_hour = int(target_time[0])
            target_min = int(target_time[1]) if len(target_time) > 1 else 0
            return now.hour == target_hour and now.minute == target_min
        
        if cron.startswith("weekly:"):
            parts = cron.split(":")
            target_day = parts[1]  # monday, tuesday, etc
            target_hour = int(parts[2])
            target_min = int(parts[3]) if len(parts) > 3 else 0
            
            days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
            current_day = days[now.weekday()]
            
            return (current_day == target_day and 
                    now.hour == target_hour and 
                    now.minute == target_min)
        
        return False
