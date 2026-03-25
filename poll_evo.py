import urllib.request, json, sys, time
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'http://localhost:8000'

def get(path):
    try:
        with urllib.request.urlopen(f'{BASE}{path}', timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        return {'_error': str(e)}

SEP = '='*60
last_run_id = 354  # last known run id

print('Polling every 15s for new evolution activity. Ctrl+C to stop.\n')

for poll in range(40):
    time.sleep(15)

    # Engine status
    s = get('/auto-evolution/coordinated/status')
    ae = s.get('auto_evolution', {})
    print(f'[poll {poll+1:02d}] running={s.get("running")} cycles={s.get("cycle_count")} '
          f'queue={ae.get("queue_size",0)} scanning={ae.get("scanning")} '
          f'in_progress={ae.get("in_progress",0)}')

    if s.get('last_error'):
        print(f'  ENGINE ERROR: {s["last_error"]}')

    # Latest evolution runs
    obs = get('/observability/tool-evolution')
    rows = obs.get('rows', [])
    new_rows = [r for r in rows if r.get('id', 0) > last_run_id]
    if new_rows:
        print(f'  NEW RUNS ({len(new_rows)}):')
        for r in new_rows:
            print(f'    [{r.get("created_at")}] {r.get("tool_name"):30s} '
                  f'{r.get("status"):12s} step={r.get("step"):20s} '
                  f'err={str(r.get("error_message",""))[:100]}')
            last_run_id = max(last_run_id, r.get('id', 0))

    # Queue
    q = get('/auto-evolution/queue')
    queue = q.get('queue', [])
    in_prog = q.get('in_progress')
    if in_prog:
        name = in_prog.get('tool_name') if isinstance(in_prog, dict) else in_prog
        print(f'  IN PROGRESS: {name}')
    if queue:
        names = [i.get('tool_name') for i in queue]
        print(f'  QUEUED: {names}')

    # Pending evolutions (new ones)
    pe = get('/evolution/pending')
    pending = pe.get('pending_evolutions', pe) if isinstance(pe, dict) else pe
    if isinstance(pending, list) and pending:
        print(f'  PENDING APPROVALS: {[p.get("tool_name") for p in pending]}')

    # Last cycle summary
    lc = s.get('last_cycle')
    if lc:
        print(f'  LAST CYCLE: evolutions={lc.get("evolutions_triggered",0)} '
              f'improvements={lc.get("improvements_applied",0)} '
              f'gaps={lc.get("gaps_found",0)}')
    print()
