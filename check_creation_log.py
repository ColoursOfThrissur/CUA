import sqlite3
import json

conn = sqlite3.connect('data/tool_creation.db')
cursor = conn.cursor()

cursor.execute('PRAGMA table_info(tool_creations)')
cols = [col[1] for col in cursor.fetchall()]
print('Columns:', cols)

cursor.execute('SELECT * FROM tool_creations ORDER BY timestamp DESC LIMIT 3')
rows = cursor.fetchall()

print('\n=== Recent Creation Attempts ===\n')
for i, row in enumerate(rows):
    print(f'\n--- Entry {i+1} ---')
    for k, v in zip(cols, row):
        if isinstance(v, str) and len(v) > 300:
            print(f'{k}: {v[:300]}...')
        else:
            print(f'{k}: {v}')

conn.close()
