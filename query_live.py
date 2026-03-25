import urllib.request, json, sys
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'http://localhost:8000'

def get(path):
    try:
        with urllib.request.urlopen(f'{BASE}{path}', timeout=8) as r:
            return json.loads(r.read())
    except Exception as e:
        return {'_error': str(e)}

def post(path, data=None):
    try:
        body = json.dumps(data or {}).encode()
        req = urllib.request.Request(f'{BASE}{path}', data=body,
              headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read())
    except Exception as e:
        return {'_error': str(e)}

SEP = '='*60

print(f'\n{SEP}\nSYSTEM STATUS\n{SEP}')
s = get('/status')
print(json.dumps(s, indent=2)[:1500])

print(f'\n{SEP}\nCOORDINATED AUTO-EVOLUTION STATUS\n{SEP}')
s = get('/auto-evolution/coordinated/status')
print(json.dumps(s, indent=2)[:1500])

print(f'\n{SEP}\nEVOLUTION QUEUE\n{SEP}')
s = get('/auto-evolution/queue')
print(json.dumps(s, indent=2)[:1000])

print(f'\n{SEP}\nPENDING EVOLUTIONS\n{SEP}')
s = get('/evolution/pending')
if isinstance(s, list):
    print(f'Count: {len(s)}')
    for e in s:
        print(f'  tool={e.get("tool_name")} status={e.get("status")} '
              f'action={e.get("proposal",{}).get("action_type","?")} '
              f'created={str(e.get("created_at",""))[:19]}')
else:
    print(json.dumps(s, indent=2)[:800])

print(f'\n{SEP}\nCIRCUIT BREAKER - QUARANTINED\n{SEP}')
s = get('/circuit-breaker/quarantined')
print(json.dumps(s, indent=2)[:800])

print(f'\n{SEP}\nCIRCUIT BREAKER - REPUTATION\n{SEP}')
s = get('/circuit-breaker/reputation')
if isinstance(s, dict):
    # Handle both {tool: score} and {tool: {score:...}} shapes
    items = []
    for tool, val in s.items():
        if tool.startswith('_'): continue
        score = val if isinstance(val, (int, float)) else val.get('reputation_score', val.get('score', 0)) if isinstance(val, dict) else 0
        items.append((tool, score))
    for tool, score in sorted(items, key=lambda x: x[1]):
        print(f'  {tool:40s} {score}')
else:
    print(json.dumps(s, indent=2)[:600])

print(f'\n{SEP}\nQUALITY SUMMARY\n{SEP}')
s = get('/quality/summary')
print(json.dumps(s, indent=2)[:1000])

print(f'\n{SEP}\nLLM WEAK TOOLS\n{SEP}')
s = get('/quality/llm-weak')
if isinstance(s, list):
    for t in s:
        print(f'  {t.get("tool_name"):35s} cat={t.get("category")} score={t.get("health_score")}')
else:
    print(json.dumps(s, indent=2)[:600])

print(f'\n{SEP}\nLOADED TOOLS\n{SEP}')
s = get('/tools/list')
tools = s if isinstance(s, list) else s.get('tools', [])
print(f'Count: {len(tools)}')
for t in tools:
    name = t if isinstance(t, str) else t.get('name', str(t))
    print(f'  {name}')

print(f'\n{SEP}\nAUTO-EVOLUTION TRIGGERS STATUS\n{SEP}')
s = get('/auto-evolution/triggers/status')
print(json.dumps(s, indent=2)[:600])

print(f'\n{SEP}\nMETRICS SUMMARY\n{SEP}')
s = get('/metrics/summary')
print(json.dumps(s, indent=2)[:800])

print(f'\n{SEP}\nRECENT TOOL EVOLUTION OBSERVABILITY\n{SEP}')
s = get('/observability/tool-evolution')
if isinstance(s, dict):
    rows = s.get('rows', s.get('data', []))
    print(f'Total rows: {s.get("total", len(rows))}')
    for r in rows[:8]:
        print(f'  {r}')
else:
    print(json.dumps(s, indent=2)[:600])

print(f'\n{SEP}\nSETTINGS / MODEL CONFIG\n{SEP}')
s = get('/settings/config')
print(json.dumps(s, indent=2)[:600])

print('\nDone.')
