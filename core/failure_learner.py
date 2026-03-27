"""
Failure Learner - Track failed patches and learn from mistakes using centralized cua.db
"""
import json
from typing import Dict, List
from datetime import datetime

from core.cua_db import get_conn


class FailureLearner:
    """Learn from failed patches to improve future risk assessment"""
    
    def __init__(self, db_path: str = None):
        # db_path ignored — always use cua.db
        pass
    
    def log_failure(self, file_path: str, change_type: str, failure_reason: str,
                   error_message: str = "", methods_affected: List[str] = None,
                   lines_changed: int = 0, metadata: Dict = None, is_environment_failure: bool = False):
        """Log a failed patch to cua.db"""
        try:
            with get_conn() as conn:
                conn.execute(
                    "INSERT INTO failures (timestamp, file_path, change_type, failure_reason, error_message, methods_affected, lines_changed, metadata) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (datetime.now().isoformat(), file_path, change_type, failure_reason, error_message,
                     json.dumps(methods_affected or []), lines_changed, json.dumps(metadata or {}))
                )
            if not is_environment_failure:
                self._update_risk_weights(file_path, change_type, failure_reason)
        except Exception as e:
            print(f"[WARN] Failed to log failure: {e}")
    
    def _update_risk_weights(self, file_path: str, change_type: str, failure_reason: str):
        """Update risk weights based on failure patterns in cua.db"""
        try:
            with get_conn() as conn:
                patterns = [
                    f"file:{file_path}",
                    f"type:{change_type}",
                    f"reason:{failure_reason}",
                    f"file_type:{change_type}"
                ]
                
                for pattern in patterns:
                    result = conn.execute("SELECT weight, failure_count FROM risk_weights WHERE pattern = ?", (pattern,)).fetchone()
                    
                    if result:
                        weight, count = result[0], result[1]
                        new_weight = min(1.0, weight + 0.1)
                        new_count = count + 1
                        conn.execute(
                            "UPDATE risk_weights SET weight = ?, failure_count = ?, last_updated = ? WHERE pattern = ?",
                            (new_weight, new_count, datetime.now().isoformat(), pattern)
                        )
                    else:
                        conn.execute(
                            "INSERT INTO risk_weights (pattern, weight, failure_count, last_updated) VALUES (?, ?, ?, ?)",
                            (pattern, 0.2, 1, datetime.now().isoformat())
                        )
        except Exception as e:
            print(f"[WARN] Failed to update risk weights: {e}")
    
    def get_risk_weight(self, file_path: str, change_type: str) -> float:
        """Get risk weight for a file/change type combination with temporal decay from cua.db"""
        try:
            with get_conn() as conn:
                patterns = [
                    f"file:{file_path}",
                    f"type:{change_type}",
                    f"file_type:{change_type}"
                ]
                
                weights = []
                for pattern in patterns:
                    result = conn.execute("SELECT weight, last_updated FROM risk_weights WHERE pattern = ?", (pattern,)).fetchone()
                    
                    if result:
                        weight, last_updated = result[0], result[1]
                        last_date = datetime.fromisoformat(last_updated)
                        age_days = (datetime.now() - last_date).days
                        decay_factor = 0.9 ** (age_days / 30)
                        decayed_weight = weight * decay_factor
                        weights.append(min(0.8, decayed_weight))
                
                return max(weights) if weights else 0.0
        except Exception as e:
            print(f"[WARN] Failed to get risk weight: {e}")
            return 0.0
    
    def get_failure_history(self, file_path: str, limit: int = 10) -> List[Dict]:
        """Get failure history for a file from cua.db"""
        try:
            with get_conn() as conn:
                rows = conn.execute(
                    "SELECT timestamp, change_type, failure_reason, error_message, methods_affected, lines_changed FROM failures WHERE file_path = ? ORDER BY timestamp DESC LIMIT ?",
                    (file_path, limit)
                ).fetchall()
                
                return [{
                    'timestamp': row[0],
                    'change_type': row[1],
                    'failure_reason': row[2],
                    'error_message': row[3],
                    'methods_affected': json.loads(row[4]),
                    'lines_changed': row[5]
                } for row in rows]
        except Exception as e:
            print(f"[WARN] Failed to get failure history: {e}")
            return []
    
    def get_high_risk_patterns(self, threshold: float = 0.5) -> List[Dict]:
        """Get patterns with high failure rates from cua.db"""
        try:
            with get_conn() as conn:
                rows = conn.execute(
                    "SELECT pattern, weight, failure_count, last_updated FROM risk_weights WHERE weight >= ? ORDER BY weight DESC",
                    (threshold,)
                ).fetchall()
                
                return [{
                    'pattern': row[0],
                    'weight': row[1],
                    'failure_count': row[2],
                    'last_updated': row[3]
                } for row in rows]
        except Exception as e:
            print(f"[WARN] Failed to get high risk patterns: {e}")
            return []
    
    def reset_pattern(self, pattern: str):
        """Reset risk weight for a pattern (after successful fix) in cua.db"""
        try:
            with get_conn() as conn:
                conn.execute(
                    "UPDATE risk_weights SET weight = 0.2, last_updated = ? WHERE pattern = ?",
                    (datetime.now().isoformat(), pattern)
                )
        except Exception as e:
            print(f"[WARN] Failed to reset pattern: {e}")
    
    def check_consecutive_successes(self, file_path: str, change_type: str) -> int:
        """Check consecutive successes for a file/type - used for weight reset"""
        pass
    
    def get_statistics(self) -> Dict:
        """Get overall failure statistics from cua.db"""
        try:
            with get_conn() as conn:
                total_failures = conn.execute("SELECT COUNT(*) FROM failures").fetchone()[0]
                by_type = dict(conn.execute("SELECT change_type, COUNT(*) FROM failures GROUP BY change_type").fetchall())
                top_reasons = dict(conn.execute(
                    "SELECT failure_reason, COUNT(*) FROM failures GROUP BY failure_reason ORDER BY COUNT(*) DESC LIMIT 5"
                ).fetchall())
                
                return {
                    'total_failures': total_failures,
                    'by_change_type': by_type,
                    'top_failure_reasons': top_reasons
                }
        except Exception as e:
            print(f"[WARN] Failed to get statistics: {e}")
            return {'total_failures': 0, 'by_change_type': {}, 'top_failure_reasons': {}}
