"""
Migrate all legacy databases to cua.db
Consolidates conversations.db, improvement_memory.db, and other legacy DBs into single cua.db
"""
import sqlite3
import os
from datetime import datetime

def migrate_conversations():
    """Migrate conversations from conversations.db to cua.db"""
    print("\n[1/8] Migrating conversations.db...")
    
    if not os.path.exists("data/conversations.db"):
        print("  [OK] conversations.db not found, skipping")
        return
    
    try:
        # Connect to both databases
        old_conn = sqlite3.connect("data/conversations.db")
        new_conn = sqlite3.connect("data/cua.db")
        
        # Get existing session_ids in cua.db to avoid duplicates
        existing = set(row[0] for row in new_conn.execute("SELECT DISTINCT session_id FROM conversations").fetchall())
        
        # Migrate conversations
        rows = old_conn.execute("SELECT session_id, timestamp, role, content, metadata FROM conversations").fetchall()
        migrated = 0
        for row in rows:
            session_id = row[0]
            # Skip if already exists
            if session_id in existing:
                continue
            new_conn.execute(
                "INSERT INTO conversations (session_id, timestamp, role, content, metadata) VALUES (?, ?, ?, ?, ?)",
                row
            )
            migrated += 1
        
        new_conn.commit()
        old_conn.close()
        new_conn.close()
        
        print(f"  [OK] Migrated {migrated} conversations (skipped {len(rows) - migrated} duplicates)")
    except Exception as e:
        print(f"  [ERROR] Error: {e}")

def migrate_improvement_memory():
    """Migrate improvements from improvement_memory.db to cua.db"""
    print("\n[2/8] Migrating improvement_memory.db...")
    
    if not os.path.exists("data/improvement_memory.db"):
        print("  ✓ improvement_memory.db not found, skipping")
        return
    
    try:
        old_conn = sqlite3.connect("data/improvement_memory.db")
        new_conn = sqlite3.connect("data/cua.db")
        
        # Check if table exists in old db
        tables = old_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        if not any('improvements' in str(t) for t in tables):
            print("  [OK] No improvements table in old db, skipping")
            old_conn.close()
            new_conn.close()
            return
        
        # Get existing timestamps to avoid duplicates
        existing = set(row[0] for row in new_conn.execute("SELECT timestamp FROM improvements").fetchall())
        
        # Migrate improvements
        rows = old_conn.execute("""
            SELECT timestamp, file_path, change_type, description, patch, outcome, 
                   error_message, test_results, metrics 
            FROM improvements
        """).fetchall()
        
        migrated = 0
        for row in rows:
            if row[0] in existing:
                continue
            new_conn.execute("""
                INSERT INTO improvements 
                (timestamp, file_path, change_type, description, patch, outcome, 
                 error_message, test_results, metrics)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, row)
            migrated += 1
        
        new_conn.commit()
        old_conn.close()
        new_conn.close()
        
        print(f"  [OK] Migrated {migrated} improvements (skipped {len(rows) - migrated} duplicates)")
    except Exception as e:
        print(f"  [ERROR] Error: {e}")

def check_other_databases():
    """Check other legacy databases for data"""
    print("\n[3/8] Checking other legacy databases...")
    
    legacy_dbs = [
        "tool_executions.db",
        "logs.db", 
        "metrics.db",
        "plan_history.db",
        "analytics.db",
        "failure_patterns.db"
    ]
    
    for db_name in legacy_dbs:
        db_path = f"data/{db_name}"
        if not os.path.exists(db_path):
            continue
        
        try:
            conn = sqlite3.connect(db_path)
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            
            if not tables:
                print(f"  [OK] {db_name}: empty, safe to delete")
                conn.close()
                continue
            
            # Count rows in each table
            has_data = False
            for table in tables:
                table_name = table[0]
                if table_name == 'sqlite_sequence':
                    continue
                count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
                if count > 0:
                    print(f"  [WARN] {db_name}: table '{table_name}' has {count} rows")
                    has_data = True
            
            if not has_data:
                print(f"  [OK] {db_name}: no data, safe to delete")
            
            conn.close()
        except Exception as e:
            print(f"  [ERROR] {db_name}: Error checking - {e}")

def backup_legacy_databases():
    """Backup legacy databases before deletion"""
    print("\n[4/8] Creating backups...")
    
    backup_dir = f"data/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    os.makedirs(backup_dir, exist_ok=True)
    
    legacy_dbs = [
        "conversations.db",
        "improvement_memory.db",
        "tool_executions.db",
        "logs.db",
        "metrics.db",
        "plan_history.db",
        "analytics.db",
        "failure_patterns.db"
    ]
    
    backed_up = 0
    for db_name in legacy_dbs:
        src = f"data/{db_name}"
        if os.path.exists(src):
            import shutil
            dst = f"{backup_dir}/{db_name}"
            shutil.copy2(src, dst)
            backed_up += 1
    
    print(f"  [OK] Backed up {backed_up} databases to {backup_dir}")
    return backup_dir

def verify_cua_db():
    """Verify cua.db has all expected tables"""
    print("\n[5/8] Verifying cua.db structure...")
    
    expected_tables = [
        'executions', 'execution_context', 'conversations', 'sessions',
        'evolution_runs', 'evolution_artifacts', 'tool_creations', 'creation_artifacts',
        'failures', 'risk_weights', 'improvements', 'learned_patterns',
        'plan_history', 'tool_metrics_hourly', 'system_metrics_hourly',
        'auto_evolution_metrics', 'resolved_gaps', 'evolution_constraints',
        'logs', 'improvement_metrics', 'attempt_terminal_states'
    ]
    
    try:
        conn = sqlite3.connect("data/cua.db")
        tables = set(row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())
        
        missing = [t for t in expected_tables if t not in tables]
        if missing:
            print(f"  [WARN] Missing tables: {', '.join(missing)}")
        else:
            print(f"  [OK] All {len(expected_tables)} expected tables present")
        
        # Show row counts
        print("\n  Table row counts:")
        for table in sorted(tables):
            if table == 'sqlite_sequence':
                continue
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if count > 0:
                print(f"    {table}: {count} rows")
        
        conn.close()
    except Exception as e:
        print(f"  [ERROR] Error: {e}")

def remove_legacy_databases():
    """Remove legacy database files after confirmation"""
    print("\n[6/8] Removing legacy databases...")
    
    legacy_dbs = [
        "conversations.db",
        "improvement_memory.db",
        "tool_executions.db",
        "logs.db",
        "metrics.db",
        "plan_history.db",
        "analytics.db",
        "failure_patterns.db"
    ]
    
    removed = 0
    for db_name in legacy_dbs:
        db_path = f"data/{db_name}"
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
                print(f"  [OK] Removed {db_name}")
                removed += 1
            except Exception as e:
                print(f"  [ERROR] Failed to remove {db_name}: {e}")
    
    print(f"\n  [OK] Removed {removed} legacy databases")

def update_config():
    """Update config_manager.py to remove legacy db references"""
    print("\n[7/8] Updating config_manager.py...")
    
    try:
        with open("core/config_manager.py", "r") as f:
            content = f.read()
        
        # Check if already updated
        if "db_conversations" not in content:
            print("  [OK] Config already updated")
            return
        
        # Comment out legacy db paths
        content = content.replace(
            '    db_conversations: str = "data/conversations.db"',
            '    # db_conversations: str = "data/conversations.db"  # DEPRECATED: use cua.db'
        )
        
        with open("core/config_manager.py", "w") as f:
            f.write(content)
        
        print("  [OK] Updated config_manager.py")
    except Exception as e:
        print(f"  [ERROR] Error: {e}")

def main():
    print("=" * 60)
    print("CUA Database Migration - Consolidate to cua.db")
    print("=" * 60)
    
    # Step 1-2: Migrate data
    migrate_conversations()
    migrate_improvement_memory()
    
    # Step 3: Check other databases
    check_other_databases()
    
    # Step 4: Backup
    backup_dir = backup_legacy_databases()
    
    # Step 5: Verify
    verify_cua_db()
    
    # Step 6: Remove legacy databases
    print("\n" + "=" * 60)
    response = input("Remove legacy databases? (yes/no): ").strip().lower()
    if response == "yes":
        remove_legacy_databases()
        update_config()
    else:
        print("\n  [WARN] Skipped removal. Legacy databases still present.")
        print(f"  Backups saved to: {backup_dir}")
    
    print("\n[8/8] Migration complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Restart the backend: python start.py")
    print("2. Test chat functionality")
    print("3. If everything works, delete backup folder")
    print("=" * 60)

if __name__ == "__main__":
    main()
