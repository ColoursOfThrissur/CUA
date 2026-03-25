import sqlite3, json, sys, urllib.request
sys.stdout.reconfigure(encoding='utf-8')

DB = r'c:\Users\derik\Desktop\Derik\Projects\CUA\data\cua.db'
BASE = 'http://localhost:8000'

def get(path):
    try:
        with urllib.request.urlopen(f'{BASE}{path}', timeout=8) as r:
            return json.loads(r.read())
    except Exception as e:
        return {'_error': str(e)}

SEP = '='*60

# 1. Last cycle details from live API
print(f'\n{SEP}\nLAST CYCLE DETAILS\n{SEP}')
s = get('/auto-evolution/coordinated/status')
lc = s.get('last_cycle', {})
if lc:
    print(f"cycle_count:   {lc.get('cycle_count')}")
    print(f"started_at:    {lc.get('started_at')}")
    print(f"finished_at:   {lc.get('finished_at')}")
    print(f"baseline_ok:   {lc.get('baseline_ok')}")
    print(f"\nauto_evolution: {json.dumps(lc.get('auto_evolution',{}), indent=2)}")
    print(f"\ntool_creation:  {json.dumps(lc.get('tool_creation',{}), indent=2)}")
    print(f"\ngap_summary:    {json.dumps(lc.get('gap_summary',{}), indent=2)}")
    print(f"\npending_summary:{json.dumps(lc.get('pending_summary',{}), indent=2)}")
    print(f"\nquality_gate:   {json.dumps(lc.get('quality_gate',{}), indent=2)}")
else:
    print('No last_cycle data')
    print(json.dumps(s, indent=2)[:500])

# 2. Logs - creation related
print(f'\n{SEP}\nLOGS - CREATION + GAP RELATED (last 30)\n{SEP}')
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("""
    SELECT service, level, message, created_at FROM logs
    WHERE (
        message LIKE '%creation%' OR message LIKE '%create_tool%'
        OR message LIKE '%gap%' OR message LIKE '%proactive%'
        OR message LIKE '%capability%' OR message LIKE '%CREATE::%'
        OR message LIKE '%tool creation%' OR message LIKE '%creation phase%'
        OR service LIKE '%creation%' OR service LIKE '%gap%'
    )
    AND level IN ('INFO','WARNING','ERROR','CRITICAL')
    ORDER BY created_at DESC LIMIT 30
""")
for r in cur.fetchall():
    d = dict(r)
    print(f"[{d['created_at']}] [{d['level']}] {d['service']}")
    print(f"  {d['message'][:300]}")

# 3. All logs last 10 min
print(f'\n{SEP}\nALL LOGS LAST 10 MIN\n{SEP}')
cur.execute("""
    SELECT service, level, message, created_at FROM logs
    WHERE created_at >= datetime('now', '-10 minutes')
    ORDER BY created_at DESC LIMIT 50
""")
rows = cur.fetchall()
print(f'Total recent logs: {len(rows)}')
for r in rows:
    d = dict(r)
    print(f"[{d['created_at']}] [{d['level']:8s}] {d['service']:30s} {d['message'][:200]}")

# 4. Gap tracker state
print(f'\n{SEP}\nGAP TRACKER STATE\n{SEP}')
try:
    with open(r'c:\Users\derik\Desktop\Derik\Projects\CUA\data\capability_gaps.json') as f:
        gaps = json.load(f)
    print(f'capability_gaps.json: {json.dumps(gaps, indent=2)[:1000]}')
except Exception as e:
    print(f'Error: {e}')

# 5. Resolved gaps table
print(f'\n{SEP}\nRESOLVED GAPS (last 10)\n{SEP}')
cur.execute("""
    SELECT capability, resolution_action, tool_name, resolved_at, notes
    FROM resolved_gaps ORDER BY resolved_at DESC LIMIT 10
""")
for r in cur.fetchall():
    print(dict(r))

# 6. Tool creations table
print(f'\n{SEP}\nTOOL CREATIONS (last 10)\n{SEP}')
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tool_creations'")
if cur.fetchone():
    cur.execute("""
        SELECT tool_name, status, error_message, created_at
        FROM tool_creations ORDER BY created_at DESC LIMIT 10
    """)
    for r in cur.fetchall():
        d = dict(r)
        print(f"[{d['created_at']}] {d['tool_name']} status={d['status']} err={str(d.get('error_message',''))[:100]}")
else:
    print('tool_creations table not found')

# 7. Pending tools
print(f'\n{SEP}\nPENDING TOOLS\n{SEP}')
s = get('/pending-tools/list')
if isinstance(s, list):
    print(f'Count: {len(s)}')
    for t in s[:5]:
        print(f"  {t.get('tool_name','?')} status={t.get('status','?')}")
elif isinstance(s, dict):
    items = s.get('tools', s.get('pending', []))
    print(f'Count: {len(items)}')
    for t in items[:5]:
        print(f"  {t}")
else:
    print(json.dumps(s, indent=2)[:300])

conn.close()
print('\nDone.')
