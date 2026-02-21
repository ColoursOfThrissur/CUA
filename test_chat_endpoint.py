"""Test the /chat endpoint directly"""
import requests
import json

API_URL = "http://localhost:8000"

# Test the chat endpoint
response = requests.post(
    f"{API_URL}/chat",
    json={"message": "which tools are failing", "session_id": "test-session"},
    headers={"Content-Type": "application/json"}
)

print("Status Code:", response.status_code)
print("\nResponse JSON:")
print(json.dumps(response.json(), indent=2))

# Check what was saved in database
import sqlite3
conn = sqlite3.connect('data/conversations.db')
cursor = conn.cursor()
cursor.execute('SELECT role, content FROM conversations WHERE session_id = "test-session" ORDER BY id DESC LIMIT 2')
rows = cursor.fetchall()
print("\n=== Database Content ===")
for row in rows:
    print(f"{row[0]}: {row[1][:200]}")
conn.close()
