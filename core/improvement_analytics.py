"""
Improvement Analytics - Track success/failure metrics
"""
import sqlite3
from pathlib import Path
from typing import Dict, List
from datetime import datetime, timedelta

class ImprovementAnalytics:
    def __init__(self, db_path: str = None):
        from core.config_manager import get_config
        config = get_config()
        self.db_path = Path(db_path or config.db_analytics)
        self.db_path.parent.mkdir(exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize analytics database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS improvement_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                iteration INTEGER,
                proposal_desc TEXT,
                risk_level TEXT,
                test_passed BOOLEAN,
                apply_success BOOLEAN,
                duration_seconds REAL,
                error_type TEXT
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp 
            ON improvement_metrics(timestamp DESC)
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attempt_terminal_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                iteration INTEGER,
                file_path TEXT,
                status TEXT,
                generated BOOLEAN,
                sandbox_passed BOOLEAN,
                applied BOOLEAN
            )
        """)
        
        conn.commit()
        conn.close()
    
    def record_attempt(self, iteration: int, proposal_desc: str, risk_level: str,
                      test_passed: bool, apply_success: bool, duration: float,
                      error_type: str = None):
        """Record improvement attempt with transaction"""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO improvement_metrics 
                (timestamp, iteration, proposal_desc, risk_level, test_passed, 
                 apply_success, duration_seconds, error_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().timestamp(),
                iteration,
                proposal_desc[:200],  # Limit description length
                risk_level,
                test_passed,
                apply_success,
                duration,
                error_type[:100] if error_type else None  # Limit error length
            ))
            
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            conn.close()
    
    def get_stats(self, days: int = 30) -> Dict:
        """Get analytics statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff = (datetime.now() - timedelta(days=days)).timestamp()
        
        # Overall success rate
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN apply_success = 1 THEN 1 ELSE 0 END) as successful,
                AVG(duration_seconds) as avg_duration
            FROM improvement_metrics
            WHERE timestamp > ?
        """, (cutoff,))
        
        row = cursor.fetchone()
        total = row[0] or 0
        successful = row[1] or 0
        avg_duration = row[2] or 0
        
        # Risk level distribution
        cursor.execute("""
            SELECT risk_level, COUNT(*) as count
            FROM improvement_metrics
            WHERE timestamp > ?
            GROUP BY risk_level
        """, (cutoff,))
        
        risk_dist = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Common errors
        cursor.execute("""
            SELECT error_type, COUNT(*) as count
            FROM improvement_metrics
            WHERE timestamp > ? AND error_type IS NOT NULL
            GROUP BY error_type
            ORDER BY count DESC
            LIMIT 5
        """, (cutoff,))
        
        common_errors = [{"error": row[0], "count": row[1]} for row in cursor.fetchall()]
        
        # Daily trend
        cursor.execute("""
            SELECT 
                DATE(timestamp, 'unixepoch') as date,
                COUNT(*) as attempts,
                SUM(CASE WHEN apply_success = 1 THEN 1 ELSE 0 END) as successes
            FROM improvement_metrics
            WHERE timestamp > ?
            GROUP BY date
            ORDER BY date DESC
            LIMIT 30
        """, (cutoff,))
        
        daily_trend = [
            {"date": row[0], "attempts": row[1], "successes": row[2]}
            for row in cursor.fetchall()
        ]
        
        conn.close()
        
        return {
            "total_attempts": total,
            "successful_attempts": successful,
            "success_rate": (successful / total * 100) if total > 0 else 0,
            "avg_duration_seconds": round(avg_duration, 2),
            "risk_distribution": risk_dist,
            "common_errors": common_errors,
            "daily_trend": daily_trend
        }

    def record_terminal_state(self, iteration: int, file_path: str, status: str, generated: bool, sandbox_passed: bool, applied: bool):
        """Persist normalized terminal state for each attempt."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO attempt_terminal_states
                (timestamp, iteration, file_path, status, generated, sandbox_passed, applied)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().timestamp(),
                iteration,
                file_path,
                status,
                generated,
                sandbox_passed,
                applied
            ))
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            conn.close()
