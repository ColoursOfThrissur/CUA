"""Scheduled triggers for auto-evolution - runs scans on schedule."""
import asyncio
import logging
from datetime import datetime, time as dt_time
from typing import Optional, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class TriggerType(Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    INTERVAL = "interval"
    FAILURE_THRESHOLD = "failure_threshold"


class AutoEvolutionTrigger:
    """Manages scheduled and event-based triggers for auto-evolution"""
    
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        self.running = False
        self.triggers = {
            "daily": {"enabled": False, "time": "02:00"},
            "weekly": {"enabled": False, "day": "sunday", "time": "02:00"},
            "interval": {"enabled": False, "hours": 6},
            "failure_threshold": {"enabled": True, "failures": 5, "window_minutes": 60}
        }
        self.failure_counts = {}
        
    async def start(self):
        """Start trigger monitoring"""
        self.running = True
        logger.info("Auto-evolution triggers started")
        
        asyncio.create_task(self._daily_trigger_loop())
        asyncio.create_task(self._interval_trigger_loop())
        asyncio.create_task(self._failure_monitor_loop())
        
    async def stop(self):
        """Stop trigger monitoring"""
        self.running = False
        logger.info("Auto-evolution triggers stopped")
        
    async def _daily_trigger_loop(self):
        """Check for daily trigger"""
        while self.running:
            try:
                if self.triggers["daily"]["enabled"]:
                    target_time = self.triggers["daily"]["time"]
                    if self._is_time_to_run(target_time):
                        logger.info("Daily trigger activated")
                        await self.orchestrator._scan_and_queue()
                        await asyncio.sleep(3600)  # Wait 1 hour before checking again
                        
                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Daily trigger error: {e}")
                await asyncio.sleep(60)
                
    async def _interval_trigger_loop(self):
        """Check for interval trigger"""
        while self.running:
            try:
                if self.triggers["interval"]["enabled"]:
                    hours = self.triggers["interval"]["hours"]
                    await asyncio.sleep(hours * 3600)  # wait first, then scan
                    if self.running and self.triggers["interval"]["enabled"]:
                        logger.info(f"Interval trigger activated ({hours}h)")
                        await self.orchestrator._scan_and_queue()
                else:
                    await asyncio.sleep(300)  # Check every 5 minutes
            except Exception as e:
                logger.error(f"Interval trigger error: {e}")
                await asyncio.sleep(300)
                
    async def _failure_monitor_loop(self):
        """Monitor tool failures and trigger evolution"""
        while self.running:
            try:
                if self.triggers["failure_threshold"]["enabled"]:
                    await self._check_failure_threshold()
                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Failure monitor error: {e}")
                await asyncio.sleep(60)
                
    async def _check_failure_threshold(self):
        """Check if any tool exceeded failure threshold"""
        from core.circuit_breaker import get_circuit_breaker
        
        cb = get_circuit_breaker()
        threshold = self.triggers["failure_threshold"]["failures"]
        
        for tool_name, circuit in cb.circuits.items():
            if circuit.failure_count >= threshold:
                # Check if already queued
                if not self.orchestrator.queue.is_queued(tool_name):
                    logger.warning(f"Failure threshold triggered for {tool_name} ({circuit.failure_count} failures)")
                    
                    from core.evolution_queue import QueuedEvolution
                    evolution = QueuedEvolution(
                        tool_name=tool_name,
                        urgency_score=100.0,
                        impact_score=80.0,
                        feasibility_score=70.0,
                        timing_score=100.0,
                        reason=f"Failure threshold exceeded ({circuit.failure_count} failures)",
                        metadata={"trigger": "failure_threshold", "failures": circuit.failure_count}
                    )
                    self.orchestrator.queue.add(evolution)
                    
    def _is_time_to_run(self, target_time: str) -> bool:
        """Check if current time matches target time (HH:MM format)"""
        now = datetime.now()
        target = datetime.strptime(target_time, "%H:%M").time()
        current = now.time()
        
        # Check if within 1 minute of target
        return (current.hour == target.hour and 
                abs(current.minute - target.minute) <= 1)
                
    def enable_trigger(self, trigger_type: str, **config):
        """Enable a trigger with configuration"""
        if trigger_type in self.triggers:
            self.triggers[trigger_type]["enabled"] = True
            self.triggers[trigger_type].update(config)
            logger.info(f"Enabled trigger: {trigger_type} with config {config}")
            
    def disable_trigger(self, trigger_type: str):
        """Disable a trigger"""
        if trigger_type in self.triggers:
            self.triggers[trigger_type]["enabled"] = False
            logger.info(f"Disabled trigger: {trigger_type}")
            
    def get_status(self) -> dict:
        """Get trigger status"""
        return {
            "running": self.running,
            "triggers": self.triggers
        }
