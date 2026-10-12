import json
import urllib.request

body = json.dumps({"text": "今天练胸，安排几个动作"}, ensure_ascii=False).encode("utf-8")
req = urllib.request.Request(
    "http://127.0.0.1:8000/api/chat",
    data=body,
    method="POST",
    headers={
        "Authorization": "Bearer dev-token",
        "Content-Type": "application/json; charset=utf-8",
    },
)
with urllib.request.urlopen(req, timeout=120) as resp:
    data = json.loads(resp.read().decode("utf-8"))
print("trace_id:", data.get("trace_id"))
for b in data.get("blocks", []):
    if b.get("kind") == "text":
        print("TEXT:", b.get("text", "")[:200])
    if b.get("kind") == "card":
        print("CARD:", b.get("title"), "items=", len(b.get("items") or []))
        for it in (b.get("items") or [])[:4]:
            print(" -", it.get("title"), it.get("subtitle"))
