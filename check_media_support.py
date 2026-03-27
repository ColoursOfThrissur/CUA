import sys, os, re
sys.stdout.reconfigure(encoding='utf-8')

keywords = ['image', 'pdf', 'vision', 'ocr', 'document', 'multimodal',
            'base64', 'PIL', 'pillow', 'photo', 'scan', 'docx', 'xlsx',
            'attachment', 'upload', 'binary', 'content.type', 'file.input']

print('=== TOOL FILES ===')
for root, dirs, files in os.walk('tools'):
    dirs[:] = [d for d in dirs if not d.startswith('__')]
    for f in files:
        if not f.endswith('.py'): continue
        path = os.path.join(root, f)
        content = open(path, encoding='utf-8', errors='replace').read().lower()
        hits = [k for k in keywords if k in content]
        if hits:
            print(f'  {path}: {hits}')

print()
print('=== LLM CLIENT (planner/llm_client.py) ===')
c = open('planner/llm_client.py', encoding='utf-8', errors='replace').read()
cl = c.lower()
hits = [k for k in ['image', 'vision', 'multimodal', 'base64', 'images', 'content_type', 'file'] if k in cl]
print(f'  keywords found: {hits}')
# Show _call_llm signature
idx = c.find('def _call_llm')
if idx >= 0:
    print(f'  _call_llm signature: {c[idx:idx+120].strip()}')
idx2 = c.find('def generate')
if idx2 >= 0:
    print(f'  generate signature: {c[idx2:idx2+120].strip()}')

print()
print('=== CHAT ENDPOINT (api/server.py) ===')
c = open('api/server.py', encoding='utf-8', errors='replace').read()
cl = c.lower()
hits = [k for k in ['image', 'vision', 'multimodal', 'base64', 'file', 'upload', 'attachment', 'form'] if k in cl]
print(f'  keywords found: {hits}')
# Show /chat route definition
idx = c.find('async def chat')
if idx < 0:
    idx = c.find('def chat(')
if idx >= 0:
    print(f'  chat handler: {c[idx:idx+300].strip()}')

print()
print('=== CHAT HELPERS (api/chat_helpers.py) ===')
try:
    c = open('api/chat_helpers.py', encoding='utf-8', errors='replace').read()
    cl = c.lower()
    hits = [k for k in ['image', 'vision', 'multimodal', 'base64', 'file', 'upload', 'attachment'] if k in cl]
    print(f'  keywords found: {hits}')
except:
    print('  not found')

print()
print('=== MCP SERVERS ENABLED ===')
import yaml
cfg = yaml.safe_load(open('config.yaml'))
for s in cfg.get('mcp_servers', []):
    if s.get('enabled'):
        print(f"  {s['name']}: {s.get('command','')}")

print()
print('=== FILESYSTEM TOOL CAPABILITIES ===')
c = open('tools/enhanced_filesystem_tool.py', encoding='utf-8', errors='replace').read()
caps = re.findall(r"name=['\"](\w+)['\"]", c)
print(f'  capabilities: {caps}')
