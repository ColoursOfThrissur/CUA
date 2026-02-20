"""Migrate database to add risk_score column."""
import sqlite3
from pathlib import Path


def migrate_database():
    """Add risk_score column to existing executions table."""
    db_path = Path("data/tool_executions.db")
    
    if not db_path.exists():
        print(f"[INFO] Database not found: {db_path}")
        print("[INFO] Will be created with new schema on first use")
        return
    
    print(f"[INFO] Migrating database: {db_path}")
    
    with sqlite3.connect(db_path) as conn:
        # Check if risk_score column exists
        cursor = conn.execute("PRAGMA table_info(executions)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if "risk_score" in columns:
            print("[OK] risk_score column already exists")
            return
        
        print("[INFO] Adding risk_score column...")
        
        # Add column with default value
        conn.execute("ALTER TABLE executions ADD COLUMN risk_score REAL DEFAULT 0.0")
        
        # Recalculate risk scores for existing records
        print("[INFO] Recalculating risk scores for existing records...")
        
        cursor = conn.execute("SELECT id, success, error, execution_time_ms, output_size FROM executions")
        records = cursor.fetchall()
        
        for record_id, success, error, exec_time, output_size in records:
            risk_score = calculate_risk_score(success, error, exec_time or 0, output_size or 0)
            conn.execute("UPDATE executions SET risk_score = ? WHERE id = ?", (risk_score, record_id))
        
        conn.commit()
        print(f"[OK] Updated {len(records)} records with risk scores")
        print("[SUCCESS] Migration complete!")


def calculate_risk_score(success: int, error: str, exec_time_ms: float, output_size: int) -> float:
    """Calculate risk score for execution (0-1, higher = riskier)."""
    risk = 0.0
    
    # Failure adds high risk
    if not success:
        risk += 0.5
        
        # Critical errors add more risk
        if error:
            error_lower = error.lower()
            if any(kw in error_lower for kw in ['timeout', 'memory', 'crash', 'fatal']):
                risk += 0.3
            elif any(kw in error_lower for kw in ['permission', 'access', 'denied']):
                risk += 0.2
    
    # Slow execution adds risk
    if exec_time_ms > 5000:
        risk += 0.2
    elif exec_time_ms > 2000:
        risk += 0.1
    
    # No output adds risk
    if output_size == 0:
        risk += 0.1
    
    return min(risk, 1.0)


if __name__ == "__main__":
    migrate_database()
