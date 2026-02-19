"""
Improvement Memory System - Tracks past improvement attempts and outcomes
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

class ImprovementMemory:
    def __init__(self, db_path: str = "data/improvement_memory.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS improvements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                file_path TEXT NOT NULL,
                change_type TEXT NOT NULL,
                description TEXT,
                patch TEXT,
                outcome TEXT NOT NULL,
                error_message TEXT,
                test_results TEXT,
                metrics TEXT
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_file_path ON improvements(file_path)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_outcome ON improvements(outcome)
        """)
        
        conn.commit()
        conn.close()
    
    def store_attempt(self, file_path: str, change_type: str, description: str,
                     patch: str, outcome: str, error_message: str = None,
                     test_results: dict = None, metrics: dict = None):
        """Store an improvement attempt"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO improvements 
            (timestamp, file_path, change_type, description, patch, outcome, 
             error_message, test_results, metrics)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            file_path,
            change_type,
            description,
            patch,
            outcome,
            error_message,
            json.dumps(test_results) if test_results else None,
            json.dumps(metrics) if metrics else None
        ))
        
        conn.commit()
        conn.close()
    
    def get_similar_attempts(self, file_path: str, limit: int = 5) -> List[Dict]:
        """Get similar past attempts for a file"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT timestamp, change_type, description, outcome, error_message
            FROM improvements
            WHERE file_path = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (file_path, limit))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'timestamp': row[0],
                'change_type': row[1],
                'description': row[2],
                'outcome': row[3],
                'error_message': row[4]
            })
        
        conn.close()
        return results
    
    def get_failed_attempts(self, days: int = 7) -> List[Dict]:
        """Get recent failed attempts"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT file_path, change_type, description, error_message
            FROM improvements
            WHERE outcome = 'failed'
            AND datetime(timestamp) > datetime('now', '-' || ? || ' days')
            ORDER BY timestamp DESC
        """, (days,))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'file_path': row[0],
                'change_type': row[1],
                'description': row[2],
                'error_message': row[3]
            })
        
        conn.close()
        return results
    
    def get_success_rate(self, file_path: str = None) -> float:
        """Calculate success rate for a file or overall"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if file_path:
            cursor.execute("""
                SELECT 
                    SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as rate
                FROM improvements
                WHERE file_path = ?
            """, (file_path,))
        else:
            cursor.execute("""
                SELECT 
                    SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as rate
                FROM improvements
            """)
        
        result = cursor.fetchone()[0] or 0.0
        conn.close()
        return result
