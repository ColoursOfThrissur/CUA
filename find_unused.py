import os
import re

# Get all core files
core_files = {f[:-3] for f in os.listdir('core') if f.endswith('.py') and f != '__init__.py'}

# Search for imports in key files
search_paths = ['api', 'core', 'planner', 'tools']
used = set()

for path in search_paths:
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith('.py'):
                try:
                    with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                        content = f.read()
                        # Find imports like: from core.X import, import core.X
                        for cf in core_files:
                            if f'core.{cf}' in content or f'core/{cf}' in content or f'core\\{cf}' in content:
                                used.add(cf)
                except:
                    pass

unused = sorted(core_files - used)

print(f'Total core files: {len(core_files)}')
print(f'Used: {len(used)}')
print(f'Potentially unused: {len(unused)}\n')
print('Unused files:')
for f in unused:
    print(f'  {f}.py')
