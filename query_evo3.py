import sqlite3, json, sys
sys.stdout.reconfigure(encoding='utf-8')

DB = r'c:\Users\derik\Desktop\Derik\Projects\CUA\data\cua.db'
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

SEP = "="*70

# 1. All evolution runs last 48h with status
print(f"\n{SEP}\nEVOLUTION RUNS - LAST 48H (all)\n{SEP}")
cur.execute("""
    SELECT tool_name, status, step, error_message, health_before, health_after, created_at
    FROM evolution_runs
    ORDER BY created_at DESC LIMIT 40
""")
runs = cur.fetchall()
for r in runs:
    d = dict(r)
    line = f"[{d['created_at']}] {d['tool_name']:35s} status={d['status']:12s} step={d['step']:20s} hB={d['health_before']} hA={d['health_after']}"
    print(line)
    if d['error_message']:
        print(f"  ERR: {d['error_message'][:200]}")

# 2. Failure breakdown by step
print(f"\n{SEP}\nFAILURE BREAKDOWN BY STEP\n{SEP}")
cur.execute("""
    SELECT step, COUNT(*) as cnt, GROUP_CONCAT(DISTINCT tool_name) as tools
    FROM evolution_runs WHERE status='failed'
    GROUP BY step ORDER BY cnt DESC
""")
for r in cur.fetchall():
    d = dict(r)
    print(f"  step={d['step']:25s} count={d['cnt']:3d}  tools={d['tools']}")

# 3. Per-tool failure summary
print(f"\n{SEP}\nPER-TOOL FAILURE SUMMARY\n{SEP}")
cur.execute("""
    SELECT tool_name,
           COUNT(*) as total,
           SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed,
           SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) as success,
           MAX(created_at) as last_run
    FROM evolution_runs
    GROUP BY tool_name
    ORDER BY failed DESC, total DESC
""")
for r in cur.fetchall():
    d = dict(r)
    print(f"  {d['tool_name']:35s} total={d['total']:3d} failed={d['failed']:3d} success={d['success']:3d}  last={d['last_run']}")

# 4. Full sandbox failure details for each failing tool
print(f"\n{SEP}\nSANDBOX FAILURE DETAILS (last 2 per tool)\n{SEP}")
cur.execute("""
    SELECT DISTINCT er.tool_name FROM evolution_runs er
    WHERE er.status='failed' AND er.step='sandbox'
    ORDER BY er.created_at DESC LIMIT 10
""")
failing_tools = [r[0] for r in cur.fetchall()]

for tool in failing_tools:
    print(f"\n--- {tool} ---")
    cur.execute("""
        SELECT ea.step, ea.artifact_type, ea.content, ea.created_at
        FROM evolution_artifacts ea
        JOIN evolution_runs er ON ea.evolution_id = er.id
        WHERE er.tool_name=? AND ea.artifact_type IN ('sandbox','validation','improved_code')
        ORDER BY ea.created_at DESC LIMIT 6
    """, (tool,))
    for r in cur.fetchall():
        d = dict(r)
        if d['artifact_type'] == 'sandbox':
            try:
                c = json.loads(d['content'])
                print(f"  [{d['created_at']}] SANDBOX step={d['step']} passed={c.get('passed')}")
                print(f"    {c.get('output','')[:500]}")
            except:
                print(f"  SANDBOX: {d['content'][:300]}")
        elif d['artifact_type'] == 'validation':
            try:
                c = json.loads(d['content'])
                if not c.get('is_valid'):
                    print(f"  [{d['created_at']}] VALIDATION FAILED: {c.get('error','')[:300]}")
            except:
                pass
        elif d['artifact_type'] == 'improved_code':
            print(f"  [{d['created_at']}] IMPROVED_CODE step={d['step']} len={len(d['content'] or '')}")

# 5. Validation failures (not sandbox)
print(f"\n{SEP}\nVALIDATION FAILURES (last 15)\n{SEP}")
cur.execute("""
    SELECT er.tool_name, ea.step, ea.content, ea.created_at
    FROM evolution_artifacts ea
    JOIN evolution_runs er ON ea.evolution_id = er.id
    WHERE ea.artifact_type='validation'
    ORDER BY ea.created_at DESC LIMIT 30
""")
for r in cur.fetchall():
    d = dict(r)
    try:
        c = json.loads(d['content'])
        if not c.get('is_valid'):
            print(f"[{d['created_at']}] {d['tool_name']:35s} step={d['step']}")
            print(f"  ERROR: {c.get('error','')[:300]}")
    except:
        pass

# 6. Proposal details for recently failed tools
print(f"\n{SEP}\nPROPOSALS FOR RECENTLY FAILED TOOLS\n{SEP}")
cur.execute("""
    SELECT DISTINCT er.tool_name FROM evolution_runs er
    WHERE er.status='failed'
    ORDER BY er.created_at DESC LIMIT 6
""")
failed_tools = [r[0] for r in cur.fetchall()]
for tool in failed_tools:
    cur.execute("""
        SELECT ea.content, ea.created_at FROM evolution_artifacts ea
        JOIN evolution_runs er ON ea.evolution_id = er.id
        WHERE er.tool_name=? AND ea.artifact_type='proposal'
        ORDER BY ea.created_at DESC LIMIT 1
    """, (tool,))
    row = cur.fetchone()
    if row:
        d = dict(row)
        try:
            p = json.loads(d['content'])
            print(f"\n[{d['created_at']}] {tool}")
            print(f"  action={p.get('action_type')} confidence={p.get('confidence')}")
            print(f"  desc={p.get('description','')[:150]}")
            print(f"  targets={p.get('target_functions')}")
            print(f"  changes={[c[:80] for c in (p.get('changes') or [])[:3]]}")
        except:
            print(f"\n{tool}: {str(d['content'])[:200]}")

# 7. Error patterns from logs
print(f"\n{SEP}\nERROR LOGS - EVOLUTION RELATED (last 20)\n{SEP}")
cur.execute("""
    SELECT service, level, message, created_at FROM logs
    WHERE level IN ('ERROR','WARNING','CRITICAL')
      AND (service LIKE '%evolution%' OR service LIKE '%sandbox%'
           OR service LIKE '%validator%' OR service LIKE '%generator%'
           OR message LIKE '%evolution%' OR message LIKE '%sandbox%'
           OR message LIKE '%Validation%' OR message LIKE '%failed%')
    ORDER BY created_at DESC LIMIT 20
""")
for r in cur.fetchall():
    d = dict(r)
    print(f"[{d['created_at']}] [{d['level']}] {d['service']}")
    print(f"  {d['message'][:300]}")

# 8. Pending evolutions status
print(f"\n{SEP}\nPENDING EVOLUTIONS\n{SEP}")
try:
    with open(r'c:\Users\derik\Desktop\Derik\Projects\CUA\data\pending_evolutions.json') as f:
        pending = json.load(f)
    if isinstance(pending, dict):
        print(f"Total pending: {len(pending)}")
        for k, v in pending.items():
            print(f"\n  tool={k} status={v.get('status')} action={v.get('proposal',{}).get('action_type','?')}")
            print(f"  desc={str(v.get('proposal',{}).get('description',''))[:120]}")
            if v.get('error'):
                print(f"  ERROR: {str(v['error'])[:200]}")
    elif isinstance(pending, list):
        print(f"Total pending: {len(pending)}")
        for p in pending[:8]:
            print(f"  tool={p.get('tool_name')} status={p.get('status')}")
except Exception as e:
    print(f"Could not read pending_evolutions.json: {e}")

conn.close()
print(f"\n{SEP}\nDone.\n{SEP}")
