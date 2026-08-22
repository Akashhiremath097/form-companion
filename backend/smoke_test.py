"""Quick end-to-end check of the chat routes. Run: python smoke_test.py"""
import sys
sys.path.insert(0, ".")

from fastapi.testclient import TestClient
import main

client = TestClient(main.app)

session = client.post("/api/sessions").json()
sid = session["session_id"]
print("START:", session["current_field"]["id"])

replies = ["Akash Hiremath", "15/03/2004", "12345", "9876543210", "skip"]
for reply in replies:
    result = client.post(f"/api/sessions/{sid}/answer", json={"reply": reply}).json()
    print(f"  {reply:18} accepted={result['accepted']}  -> {result['message'][:50]}")

preview = client.get(f"/api/sessions/{sid}/preview").json()
print("PROGRESS:", preview["progress"])