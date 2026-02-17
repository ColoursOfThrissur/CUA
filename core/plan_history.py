"""
Plan History - Track and rollback executed plans
"""
import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

class PlanHistory:
    def __init__(self, db_path: str = None):
        from core.config_manager import get_config
        config = get_config()
        self.db_path = Path(db_path or config.db_plan_history)
        self.db_path.parent.mkdir(exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS plan_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id TEXT UNIQUE NOT NULL,
                timestamp REAL NOT NULL,
                iteration INTEGER,
                description TEXT,
                proposal TEXT NOT NULL,
                patch TEXT,
                risk_level TEXT,
                test_result TEXT,
                apply_result TEXT,
                status TEXT,
                rollback_commit TEXT
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp 
            ON plan_history(timestamp DESC)
        """)
        
        conn.commit()
        conn.close()
    
    def save_plan(self, plan_id: str, iteration: int, proposal: Dict, 
                  risk_level: str, test_result: Dict, apply_result: Dict):
        """Save executed plan to history"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO plan_history 
            (plan_id, timestamp, iteration, description, proposal, patch, 
             risk_level, test_result, apply_result, status, rollback_commit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            plan_id,
            datetime.now().timestamp(),
            iteration,
            proposal.get('description', ''),
            json.dumps(proposal),
            proposal.get('patch', ''),
            risk_level,
            json.dumps(test_result),
            json.dumps(apply_result),
            'applied' if apply_result.get('success') else 'failed',
            apply_result.get('backup_id', '')
        ))
        
        conn.commit()
        conn.close()
    
    def get_history(self, limit: int = 50) -> List[Dict]:
        """Get plan execution history"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT plan_id, timestamp, iteration, description, risk_level, 
                   status, rollback_commit
            FROM plan_history
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [{
            "plan_id": row[0],
            "timestamp": row[1],
            "iteration": row[2],
            "description": row[3],
            "risk_level": row[4],
            "status": row[5],
            "rollback_commit": row[6]
        } for row in rows]
    
    def get_plan(self, plan_id: str) -> Optional[Dict]:
        """Get full plan details"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM plan_history WHERE plan_id = ?
        """, (plan_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return {
            "plan_id": row[1],
            "timestamp": row[2],
            "iteration": row[3],
            "description": row[4],
            "proposal": json.loads(row[5]),
            "patch": row[6],
            "risk_level": row[7],
            "test_result": json.loads(row[8]),
            "apply_result": json.loads(row[9]),
            "status": row[10],
            "backup_id": row[11]  # DB column is rollback_commit, aliased as backup_id
        }
