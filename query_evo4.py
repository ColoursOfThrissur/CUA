import sqlite3, json, sys
sys.stdout.reconfigure(encoding='utf-8')

DB = r'c:\Users\derik\Desktop\Derik\Projects\CUA\data\cua.db'
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

SEP = "="*70

# BrowserAutomationTool - code_generation failures (empty code + syntax error)
print(f"\n{SEP}\nBROWSERATOMATIONTOOL - CODE GENERATION FAILURES\n{SEP}")
cur.execute("""
    SELECT er.id, er.error_message, er.created_at FROM evolution_runs er
    WHERE er.tool_name='BrowserAutomationTool' AND er.status='failed'
    ORDER BY er.created_at DESC LIMIT 5
""")
for run in cur.fetchall():
    d = dict(run)
    print(f"\n[{d['created_at']}] ERR: {d['error_message']}")
    # Get proposal for this run
    cur.execute("""
        SELECT artifact_type, step, content FROM evolution_artifacts
        WHERE evolution_id=? ORDER BY created_at ASC
    """, (d['id'],))
    for a in cur.fetchall():
        ad = dict(a)
        if ad['artifact_type'] == 'proposal':
            try:
                p = json.loads(ad['content'])
                print(f"  PROPOSAL: action={p.get('action_type')} target={p.get('target_functions')}")
                print(f"  DESC: {p.get('description','')[:200]}")
                sketch = p.get('implementation_sketch') or {}
                for fn, steps in sketch.items():
                    print(f"  SKETCH[{fn}]: {steps[:3]}")
            except: pass
        elif ad['artifact_type'] == 'improved_code':
            code = ad['content'] or ''
            print(f"  CODE len={len(code)} step={ad['step']}")
            if code:
                print(f"  CODE PREVIEW:\n{code[:600]}")
        elif ad['artifact_type'] == 'error':
            try:
                e = json.loads(ad['content'])
                print(f"  ERROR artifact step={ad['step']}: {e.get('error','')[:200]}")
            except:
                print(f"  ERROR artifact: {ad['content'][:200]}")

# MCPAdapterTool - analysis failures
print(f"\n{SEP}\nMCPADAPTERTOOL - ANALYSIS FAILURES\n{SEP}")
cur.execute("""
    SELECT er.id, er.error_message, er.created_at FROM evolution_runs er
    WHERE er.tool_name='MCPAdapterTool' AND er.status='failed'
    ORDER BY er.created_at DESC LIMIT 3
""")
for run in cur.fetchall():
    d = dict(run)
    print(f"\n[{d['created_at']}] ERR: {d['error_message']}")
    cur.execute("""
        SELECT artifact_type, step, content FROM evolution_artifacts
        WHERE evolution_id=? ORDER BY created_at ASC
    """, (d['id'],))
    for a in cur.fetchall():
        ad = dict(a)
        if ad['artifact_type'] == 'error':
            try:
                e = json.loads(ad['content'])
                print(f"  ERROR step={ad['step']}: {e.get('error','')[:300]}")
            except:
                print(f"  ERROR: {ad['content'][:300]}")

# Check if MCPAdapterTool file exists and what it looks like
print(f"\n{SEP}\nMCPADAPTERTOOL FILE CHECK\n{SEP}")
import os
for p in ['tools/MCPAdapterTool.py','tools/experimental/MCPAdapterTool.py',
          'tools/mcp_adapter_tool.py','core/mcp_adapter.py']:
    exists = os.path.exists(p)
    print(f"  {p}: {'EXISTS' if exists else 'not found'}")

# Check tool_registry for MCPAdapterTool
try:
    with open('data/tool_registry.json') as f:
        reg = json.load(f)
    mcp_entries = {k:v for k,v in reg.items() if 'mcp' in k.lower() or 'MCP' in k}
    print(f"\nRegistry MCP entries: {list(mcp_entries.keys())}")
    for k,v in list(mcp_entries.items())[:2]:
        print(f"  {k}: path={v.get('path','?')} status={v.get('status','?')}")
except Exception as e:
    print(f"Registry read error: {e}")

# DataTransformationTool - pandas dependency loop
print(f"\n{SEP}\nDATATRANSFORMATIONTOOL - PANDAS DEPENDENCY LOOP\n{SEP}")
cur.execute("""
    SELECT er.id, er.error_message, er.created_at FROM evolution_runs er
    WHERE er.tool_name='DataTransformationTool' AND er.status='failed'
    ORDER BY er.created_at DESC LIMIT 3
""")
for run in cur.fetchall():
    d = dict(run)
    print(f"[{d['created_at']}] ERR: {d['error_message']}")
    cur.execute("""
        SELECT artifact_type, step, content FROM evolution_artifacts
        WHERE evolution_id=? AND artifact_type='proposal'
    """, (d['id'],))
    row = cur.fetchone()
    if row:
        try:
            p = json.loads(dict(row)['content'])
            print(f"  PROPOSAL: {p.get('description','')[:150]}")
            print(f"  CHANGES: {[c[:80] for c in (p.get('changes') or [])[:3]]}")
        except: pass

# UserApprovalGateTool - file not found in sandbox
print(f"\n{SEP}\nUSERAPPROVALGATETOOL - SANDBOX FILE NOT FOUND\n{SEP}")
cur.execute("""
    SELECT er.id, er.created_at FROM evolution_runs er
    WHERE er.tool_name='UserApprovalGateTool' AND er.status='failed'
    ORDER BY er.created_at DESC LIMIT 2
""")
for run in cur.fetchall():
    d = dict(run)
    cur.execute("""
        SELECT artifact_type, step, content FROM evolution_artifacts
        WHERE evolution_id=? AND artifact_type IN ('sandbox','proposal')
        ORDER BY created_at DESC LIMIT 4
    """, (d['id'],))
    for a in cur.fetchall():
        ad = dict(a)
        if ad['artifact_type'] == 'sandbox':
            try:
                c = json.loads(ad['content'])
                print(f"[{d['created_at']}] SANDBOX passed={c.get('passed')}")
                print(f"  {c.get('output','')[:400]}")
            except: pass
        elif ad['artifact_type'] == 'proposal':
            try:
                p = json.loads(ad['content'])
                print(f"  PROPOSAL: {p.get('description','')[:150]}")
            except: pass

conn.close()
print(f"\n{SEP}\nDone.\n{SEP}")
