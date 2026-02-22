"""Metrics scheduler for automatic hourly aggregation."""
import threading
import time
import logging
from datetime import datetime
from core.metrics_aggregator import get_metrics_aggregator

logger = logging.getLogger(__name__)

class MetricsScheduler:
    """Schedules automatic metrics aggregation."""
    
    def __init__(self, interval_seconds: int = 3600):  # Default: 1 hour
        self.interval_seconds = interval_seconds
        self.running = False
        self.thread = None
        self.aggregator = get_metrics_aggregator()
    
    def start(self):
        """Start the scheduler."""
        if self.running:
            logger.warning("Metrics scheduler already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        logger.info(f"Metrics scheduler started (interval: {self.interval_seconds}s)")
    
    def stop(self):
        """Stop the scheduler."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Metrics scheduler stopped")
    
    def _run(self):
        """Main scheduler loop."""
        while self.running:
            try:
                # Wait until next hour boundary
                now = time.time()
                next_hour = ((int(now) // 3600) + 1) * 3600
                sleep_time = next_hour - now
                
                logger.info(f"Next metrics aggregation in {sleep_time:.0f} seconds")
                
                # Sleep in small intervals to allow quick shutdown
                while self.running and time.time() < next_hour:
                    time.sleep(min(60, next_hour - time.time()))
                
                if not self.running:
                    break
                
                # Run aggregation
                logger.info("Running scheduled metrics aggregation...")
                self.aggregator.run_aggregation()
                logger.info("Metrics aggregation complete")
                
            except Exception as e:
                logger.error(f"Error in metrics scheduler: {e}", exc_info=True)
                # Sleep a bit before retrying
                time.sleep(60)

_scheduler = None

def get_metrics_scheduler() -> MetricsScheduler:
    """Get singleton scheduler."""
    global _scheduler
    if _scheduler is None:
        _scheduler = MetricsScheduler()
    return _scheduler
