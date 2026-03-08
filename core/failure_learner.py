"""
Failure Learner - Track failed patches and learn from mistakes
"""
import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from core.sqlite_logging import get_logger
from core.sqlite_utils import safe_connect, safe_close

logger = get_logger("failure_learner")

class FailureLearner:
    """Learn from failed patches to improve future risk assessment"""
    
    def __init__(self, db_path: str = "data/failure_patterns.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize failure patterns database"""
        conn = safe_connect(self.db_path)
        if not conn:
            logger.warning("Failure patterns DB unavailable; failure learning disabled for now")
            return
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS failures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                file_path TEXT NOT NULL,
                change_type TEXT NOT NULL,
                failure_reason TEXT NOT NULL,
                error_message TEXT,
                methods_affected TEXT,
                lines_changed INTEGER,
                metadata TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS risk_weights (
                pattern TEXT PRIMARY KEY,
                weight REAL NOT NULL,
                failure_count INTEGER NOT NULL,
                last_updated TEXT NOT NULL
            )
        ''')
        
        conn.commit()
        safe_close(conn)
    
    def log_failure(self, file_path: str, change_type: str, failure_reason: str,
                   error_message: str = "", methods_affected: List[str] = None,
                   lines_changed: int = 0, metadata: Dict = None, is_environment_failure: bool = False):
        """Log a failed patch"""
        conn = safe_connect(self.db_path)
        if not conn:
            return
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO failures 
            (timestamp, file_path, change_type, failure_reason, error_message, 
             methods_affected, lines_changed, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now().isoformat(),
            file_path,
            change_type,
            failure_reason,
            error_message,
            json.dumps(methods_affected or []),
            lines_changed,
            json.dumps(metadata or {})
        ))
        
        conn.commit()
        safe_close(conn)
        
        # Only update risk weights for logic failures, not environment failures
        if not is_environment_failure:
            self._update_risk_weights(file_path, change_type, failure_reason)
    
    def _update_risk_weights(self, file_path: str, change_type: str, failure_reason: str):
        """Update risk weights based on failure patterns"""
        conn = safe_connect(self.db_path)
        if not conn:
            return
        cursor = conn.cursor()
        
        # Create pattern key
        patterns = [
            f"file:{file_path}",
            f"type:{change_type}",
            f"reason:{failure_reason}",
            f"file_type:{change_type}"  # Combined pattern
        ]
        
        for pattern in patterns:
            cursor.execute('''
                SELECT weight, failure_count FROM risk_weights WHERE pattern = ?
            ''', (pattern,))
            
            result = cursor.fetchone()
            
            if result:
                weight, count = result
                new_weight = min(1.0, weight + 0.1)  # Increase by 0.1, max 1.0
                new_count = count + 1
                
                cursor.execute('''
                    UPDATE risk_weights 
                    SET weight = ?, failure_count = ?, last_updated = ?
                    WHERE pattern = ?
                ''', (new_weight, new_count, datetime.now().isoformat(), pattern))
            else:
                cursor.execute('''
                    INSERT INTO risk_weights (pattern, weight, failure_count, last_updated)
                    VALUES (?, ?, ?, ?)
                ''', (pattern, 0.2, 1, datetime.now().isoformat()))
        
        conn.commit()
        safe_close(conn)
    
    def get_risk_weight(self, file_path: str, change_type: str) -> float:
        """Get risk weight for a file/change type combination with temporal decay"""
        conn = safe_connect(self.db_path)
        if not conn:
            return 0.0
        cursor = conn.cursor()
        
        patterns = [
            f"file:{file_path}",
            f"type:{change_type}",
            f"file_type:{change_type}"
        ]
        
        weights = []
        for pattern in patterns:
            cursor.execute('''
                SELECT weight, last_updated FROM risk_weights WHERE pattern = ?
            ''', (pattern,))
            
            result = cursor.fetchone()
            if result:
                weight, last_updated = result
                
                # Apply temporal decay
                from datetime import datetime
                last_date = datetime.fromisoformat(last_updated)
                age_days = (datetime.now() - last_date).days
                
                # Decay: 10% reduction per 30 days
                decay_factor = 0.9 ** (age_days / 30)
                decayed_weight = weight * decay_factor
                
                # Cap at 0.8 to prevent permanent blacklisting
                weights.append(min(0.8, decayed_weight))
        
        safe_close(conn)
        
        # Return max weight if any patterns match
        return max(weights) if weights else 0.0
    
    def get_failure_history(self, file_path: str, limit: int = 10) -> List[Dict]:
        """Get failure history for a file"""
        conn = safe_connect(self.db_path)
        if not conn:
            return []
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT timestamp, change_type, failure_reason, error_message, 
                   methods_affected, lines_changed
            FROM failures
            WHERE file_path = ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (file_path, limit))
        
        failures = []
        for row in cursor.fetchall():
            failures.append({
                'timestamp': row[0],
                'change_type': row[1],
                'failure_reason': row[2],
                'error_message': row[3],
                'methods_affected': json.loads(row[4]),
                'lines_changed': row[5]
            })
        
        safe_close(conn)
        return failures
    
    def get_high_risk_patterns(self, threshold: float = 0.5) -> List[Dict]:
        """Get patterns with high failure rates"""
        conn = safe_connect(self.db_path)
        if not conn:
            return []
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT pattern, weight, failure_count, last_updated
            FROM risk_weights
            WHERE weight >= ?
            ORDER BY weight DESC
        ''', (threshold,))
        
        patterns = []
        for row in cursor.fetchall():
            patterns.append({
                'pattern': row[0],
                'weight': row[1],
                'failure_count': row[2],
                'last_updated': row[3]
            })
        
        safe_close(conn)
        return patterns
    
    def reset_pattern(self, pattern: str):
        """Reset risk weight for a pattern (after successful fix)"""
        conn = safe_connect(self.db_path)
        if not conn:
            return
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE risk_weights 
            SET weight = 0.2, last_updated = ?
            WHERE pattern = ?
        ''', (datetime.now().isoformat(), pattern))
        
        conn.commit()
        safe_close(conn)
    
    def check_consecutive_successes(self, file_path: str, change_type: str) -> int:
        """Check consecutive successes for a file/type - used for weight reset"""
        # This would require tracking successes in addition to failures
        # For now, manual reset via reset_pattern() is sufficient
        pass
    
    def get_statistics(self) -> Dict:
        """Get overall failure statistics"""
        conn = safe_connect(self.db_path)
        if not conn:
            return {'total_failures': 0, 'by_change_type': {}, 'top_failure_reasons': {}}
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM failures')
        total_failures = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT change_type, COUNT(*) 
            FROM failures 
            GROUP BY change_type
        ''')
        by_type = dict(cursor.fetchall())
        
        cursor.execute('''
            SELECT failure_reason, COUNT(*) 
            FROM failures 
            GROUP BY failure_reason
            ORDER BY COUNT(*) DESC
            LIMIT 5
        ''')
        top_reasons = dict(cursor.fetchall())
        
        safe_close(conn)
        
        return {
            'total_failures': total_failures,
            'by_change_type': by_type,
            'top_failure_reasons': top_reasons
        }
