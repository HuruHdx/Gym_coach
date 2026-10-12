import json
import urllib.error
import urllib.request


def req(method: str, url: str, body: dict | None = None) -> None:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer dev-token",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    try:
        with urllib.request.urlopen(request) as resp:
            raw = resp.read().decode("utf-8")
            print(method, url, resp.status)
            print(raw[:1200])
    except urllib.error.HTTPError as e:
        print(method, url, "ERR", e.code, e.read().decode("utf-8", errors="replace")[:1200])


req(
    "POST",
    "http://127.0.0.1:8000/api/profile",
    {
        "goal": "增肌",
        "experience": "进阶",
        "weight_kg": 72.4,
        "days_per_week": 4,
        "injuries": ["左膝"],
    },
)
req("GET", "http://127.0.0.1:8000/api/profile")
req(
    "PATCH",
    "http://127.0.0.1:8000/api/profile",
    {"weight_kg": 73, "injuries_add": ["肩"]},
)
req("POST", "http://127.0.0.1:8000/api/chat", {"text": "今天练胸，安排几个动作"})
req("GET", "http://127.0.0.1:8000/api/debug/traces?limit=1")
