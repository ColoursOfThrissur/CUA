import urllib.request, json, sys, time
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'http://localhost:8000'

def get(path):
    try:
        with urllib.request.urlopen(f'{BASE}{path}', timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        return {'_error': str(e)}

def post(path, data=None):
    try:
        body = json.dumps(data or {}).encode()
        req = urllib.request.Request(f'{BASE}{path}', data=body,
              headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except Exception as e:
        return {'_error': str(e)}

SEP = '='*60

# 1. Full status
print(f'\n{SEP}\nFULL STATUS\n{SEP}')
s = get('/status')
print(json.dumps(s, indent=2))

# 2. Check reload_mode — this blocks the engine
print(f'\n{SEP}\nCOORDINATED STATUS (reload_mode check)\n{SEP}')
s = get('/auto-evolution/coordinated/status')
print(f"running:      {s.get('running')}")
print(f"reload_mode:  {s.get('reload_mode')}")
print(f"reload_blocked: {s.get('reload_blocked')}")
print(f"last_error:   {s.get('last_error')}")
print(f"cycle_count:  {s.get('cycle_count')}")

# 3. Try starting the coordinated engine
print(f'\n{SEP}\nSTARTING COORDINATED ENGINE\n{SEP}')
r = post('/auto-evolution/coordinated/start')
print(json.dumps(r, indent=2))

time.sleep(3)

# 4. Status after start
print(f'\n{SEP}\nSTATUS AFTER START\n{SEP}')
s = get('/auto-evolution/coordinated/status')
print(f"running:     {s.get('running')}")
print(f"cycle_count: {s.get('cycle_count')}")
print(f"last_error:  {s.get('last_error')}")

# 5. Manually trigger a scan cycle
print(f'\n{SEP}\nTRIGGERING SCAN\n{SEP}')
r = post('/auto-evolution/trigger-scan')
print(json.dumps(r, indent=2))

time.sleep(3)

# 6. Manually run one coordinated cycle
print(f'\n{SEP}\nRUNNING ONE COORDINATED CYCLE\n{SEP}')
r = post('/auto-evolution/coordinated/run-cycle')
print(json.dumps(r, indent=2)[:2000])

time.sleep(3)

# 7. Final status
print(f'\n{SEP}\nFINAL STATUS\n{SEP}')
s = get('/auto-evolution/coordinated/status')
print(f"running:     {s.get('running')}")
print(f"cycle_count: {s.get('cycle_count')}")
print(f"last_cycle:  {json.dumps(s.get('last_cycle'), indent=2)[:500] if s.get('last_cycle') else None}")
print(f"last_error:  {s.get('last_error')}")

# 8. Evolution queue after cycle
print(f'\n{SEP}\nEVOLUTION QUEUE AFTER CYCLE\n{SEP}')
s = get('/auto-evolution/queue')
q = s.get('queue', [])
print(f'Queue size: {len(q)}')
for item in q:
    print(f"  {item.get('tool_name'):35s} priority={item.get('priority_score')} status={item.get('status')}")

# 9. Latest evolution runs from observability
print(f'\n{SEP}\nLATEST EVOLUTION RUNS\n{SEP}')
s = get('/observability/tool-evolution')
rows = s.get('rows', s.get('data', []))
for r in rows[:5]:
    print(f"  [{r.get('created_at')}] {r.get('tool_name'):30s} {r.get('status'):12s} step={r.get('step')} err={str(r.get('error_message',''))[:80]}")

print('\nDone.')
