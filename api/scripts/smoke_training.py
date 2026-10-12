import httpx

h = {"Authorization": "Bearer dev-token"}
c = httpx.Client(base_url="http://127.0.0.1:8000", headers=h, timeout=30)
body = {
    "title": "胸训",
    "split_label": "胸",
    "items": [
        {
            "id": "c1",
            "title": "哑铃卧推",
            "selected": True,
            "meta": {"sets": 2, "reps": "8", "weight": 30, "muscle": "胸"},
        },
        {
            "id": "c2",
            "title": "器械夹胸",
            "selected": True,
            "meta": {"sets": 2, "reps": "12", "weight": 40, "muscle": "胸"},
        },
    ],
}
r = c.post("/api/training/adopt", json=body)
print("adopt", r.status_code)
r.raise_for_status()
s = r.json()
print("sets", len(s["sets"]), "status", s["status"])
sid = s["sets"][0]["id"]
r2 = c.patch(f"/api/training/sets/{sid}", json={"completed": True, "actual_weight": 32.5})
print("patch", r2.status_code, r2.json()["completed"], r2.json()["actual_weight"])
r3 = c.post(f"/api/training/sessions/{s['id']}/complete")
print("complete", r3.status_code, r3.json()["status"], r3.json()["progress"])
r4 = c.get("/api/training/exercises")
print("exercises", r4.json())
