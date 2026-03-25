"""
CUA Clean Reset — clears all runtime history and state.

Preserves:
  - tool_registry.json  (tool discovery)
  - credentials.enc     (encrypted API keys)
  - tools/              (tool source files — unchanged)
  - data/tool_backups/  (backup files)
  - config.yaml         (configuration)

Clears:
  - All DB tables in cua.db (logs, evolution history, executions, metrics)
  - conversations.db
  - improvement_memory.db
  - All JSON state files (pending, gaps, queue, cache, memory)
"""
import sqlite3, json, shutil, sys
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

# Safety check — must be run from project root
if not Path("core/cua_db.py").exists():
    print("ERROR: Run from CUA project root")
    sys.exit(1)

print("CUA Clean Reset")
print("="*50)
print("This will clear all runtime history.")
print("Tool files, registry, and credentials are preserved.")
print()

confirm = input("Type 'yes' to proceed: ").strip().lower()
if confirm != 'yes':
    print("Aborted.")
    sys.exit(0)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

# ── 1. Clear cua.db tables ────────────────────────────────────────────────────
print("\n[1/4] Clearing cua.db...")
conn = sqlite3.connect("data/cua.db")
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in cur.fetchall() if r[0] != 'sqlite_sequence']
PRESERVE_TABLES = set()  # nothing to preserve — all history
for table in tables:
    if table not in PRESERVE_TABLES:
        try:
            cur.execute(f"DELETE FROM {table}")
            print(f"  cleared: {table}")
        except Exception as e:
            print(f"  skip {table}: {e}")
# Reset autoincrement sequences
try:
    cur.execute("DELETE FROM sqlite_sequence")
except: pass
conn.commit()
conn.close()
print("  cua.db cleared.")

# ── 2. Clear conversations.db ─────────────────────────────────────────────────
print("\n[2/4] Clearing conversations.db...")
conn2 = sqlite3.connect("data/conversations.db")
cur2 = conn2.cursor()
cur2.execute("SELECT name FROM sqlite_master WHERE type='table'")
for (t,) in cur2.fetchall():
    if t != 'sqlite_sequence':
        try:
            cur2.execute(f"DELETE FROM {t}")
        except: pass
try:
    cur2.execute("DELETE FROM sqlite_sequence")
except: pass
conn2.commit()
conn2.close()
print("  conversations.db cleared.")

# ── 3. Clear improvement_memory.db ───────────────────────────────────────────
print("\n[3/4] Clearing improvement_memory.db...")
conn3 = sqlite3.connect("data/improvement_memory.db")
cur3 = conn3.cursor()
cur3.execute("SELECT name FROM sqlite_master WHERE type='table'")
for (t,) in cur3.fetchall():
    if t != 'sqlite_sequence':
        try:
            cur3.execute(f"DELETE FROM {t}")
        except: pass
try:
    cur3.execute("DELETE FROM sqlite_sequence")
except: pass
conn3.commit()
conn3.close()
print("  improvement_memory.db cleared.")

# ── 4. Reset JSON state files ─────────────────────────────────────────────────
print("\n[4/4] Resetting JSON state files...")

JSON_RESETS = {
    "data/pending_evolutions.json": "{}",
    "data/pending_tools.json":      '{"pending": {}, "history": []}',
    "data/capability_gaps.json":    "{}",
    "data/evolution_queue.json":    '{"queue": [], "in_progress": null, "failed": {}, "last_updated": null}',
    "data/strategic_memory.json":   "{}",
    "data/llm_health_cache.json":   "{}",
    "data/feature_tracker.json":    '{"features": [], "last_updated": null}',
    "data/growth_history.json":     "[]",
    "data/evolution_history.json":  '{"evolutions": []}',
    "data/schedules.json":          "{}",
    "data/applied_changes.json":    "[]",
    "data/pending_libraries.json":  "[]",
    "data/pending_services.json":   "[]",
    "data/pending_skills.json":     "[]",
}

for path, empty_val in JSON_RESETS.items():
    p = Path(path)
    if p.exists():
        p.write_text(empty_val)
        print(f"  reset: {p.name}")
    else:
        print(f"  skip (missing): {p.name}")

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n" + "="*50)
print("Reset complete.")
print()
print("Preserved:")
print("  data/tool_registry.json  (tool discovery)")
print("  data/credentials.enc     (API keys)")
print("  tools/                   (tool source files)")
print("  data/tool_backups/       (backup files)")
print()
print("Next steps:")
print("  1. Restart the server (start.bat or start.py)")
print("  2. The system will re-scan tools and rebuild health scores")
print("  3. Autonomy will start fresh with no history")
