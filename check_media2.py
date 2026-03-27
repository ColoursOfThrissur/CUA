import sys, re
sys.stdout.reconfigure(encoding='utf-8')

print('=== chat_helpers.py image/base64/upload sections ===')
c = open('api/chat_helpers.py', encoding='utf-8', errors='replace').read()
for kw in ['image', 'base64', 'upload', 'file']:
    for m in re.finditer(kw, c, re.IGNORECASE):
        idx = m.start()
        snippet = c[max(0,idx-80):idx+200].replace('\n',' ')
        print(f'  [{kw}] ...{snippet}...')
        print()

print()
print('=== llm_client.py full _call_llm method ===')
c2 = open('planner/llm_client.py', encoding='utf-8', errors='replace').read()
idx = c2.find('def _call_llm')
end = c2.find('\n    def ', idx+1)
print(c2[idx:end if end>0 else idx+2000])

print()
print('=== api/server.py /chat route ===')
c3 = open('api/server.py', encoding='utf-8', errors='replace').read()
idx = c3.find('@app.post')
while idx >= 0:
    chunk = c3[idx:idx+300]
    if 'chat' in chunk.lower():
        print(chunk)
        print()
    idx = c3.find('@app.post', idx+1)
