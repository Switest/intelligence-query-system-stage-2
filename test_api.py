import requests
import re as _re
import sys

BASE = "http://localhost:5000"
passed = 0
failed = 0

def check(label, resp, expected_status, checks):
    global passed, failed
    lines = []
    ok = True

    if resp.status_code != expected_status:
        lines.append(f"  HTTP {resp.status_code} (expected {expected_status})")
        ok = False

    try:
        body = resp.json()
    except Exception:
        lines.append("  Could not parse JSON")
        ok = False
        body = {}

    for desc, expr in checks:
        try:
            val = expr(body)
            if not val:
                lines.append(f"  FAIL  {desc}")
                ok = False
        except Exception as e:
            lines.append(f"  ERR   {desc} — {e}")
            ok = False

    if ok:
        passed += 1
        print(f"[PASS] {label}")
    else:
        failed += 1
        print(f"[FAIL] {label}")
        for l in lines:
            print(l)

# ── 1. Default pagination shape ────────────────────────────────────────────
r = requests.get(f"{BASE}/api/profiles")
check("Default GET /api/profiles shape", r, 200, [
    ("status=success",       lambda d: d.get("status") == "success"),
    ("page=1",               lambda d: d.get("page") == 1),
    ("limit=10",             lambda d: d.get("limit") == 10),
    ("total=2026",           lambda d: d.get("total") == 2026),
    ("data has 10 records",  lambda d: len(d.get("data", [])) == 10),
    ("id field present",     lambda d: "id" in d["data"][0]),
    ("created_at present",   lambda d: "created_at" in d["data"][0]),
])

# ── 2. Limit capped at 50 ─────────────────────────────────────────────────
r = requests.get(f"{BASE}/api/profiles", params={"limit": "100"})
check("Limit capped at 50", r, 200, [
    ("limit returned is 50",        lambda d: d.get("limit") == 50),
    ("data has exactly 50 records", lambda d: len(d.get("data", [])) == 50),
])

# ── 3. Gender filter ──────────────────────────────────────────────────────
r = requests.get(f"{BASE}/api/profiles", params={"gender": "male", "limit": "50"})
check("Filter gender=male", r, 200, [
    ("status=success",       lambda d: d.get("status") == "success"),
    ("all records are male", lambda d: all(x["gender"] == "male" for x in d["data"])),
])

# ── 4. country_id filter ──────────────────────────────────────────────────
r = requests.get(f"{BASE}/api/profiles", params={"country_id": "NG", "limit": "50"})
check("Filter country_id=NG", r, 200, [
    ("all records are NG", lambda d: all(x["country_id"] == "NG" for x in d["data"])),
])

# ── 5. age_group filter ───────────────────────────────────────────────────
r = requests.get(f"{BASE}/api/profiles", params={"age_group": "teenager", "limit": "50"})
check("Filter age_group=teenager", r, 200, [
    ("all records are teenagers", lambda d: all(x["age_group"] == "teenager" for x in d["data"])),
])

# ── 6. min_age / max_age filter ───────────────────────────────────────────
r = requests.get(f"{BASE}/api/profiles", params={"min_age": "25", "max_age": "40", "limit": "50"})
check("Filter min_age=25, max_age=40", r, 200, [
    ("all ages in 25-40 range", lambda d: all(25 <= x["age"] <= 40 for x in d["data"])),
])

# ── 7. min_gender_probability filter ──────────────────────────────────────
r = requests.get(f"{BASE}/api/profiles", params={"min_gender_probability": "0.95", "limit": "50"})
check("Filter min_gender_probability=0.95", r, 200, [
    ("all probs >= 0.95", lambda d: all(x["gender_probability"] >= 0.95 for x in d["data"])),
])

# ── 8. min_country_probability filter ────────────────────────────────────
r = requests.get(f"{BASE}/api/profiles", params={"min_country_probability": "0.90", "limit": "50"})
check("Filter min_country_probability=0.90", r, 200, [
    ("all probs >= 0.90", lambda d: all(x["country_probability"] >= 0.90 for x in d["data"])),
])

# ── 9. Combined filters ───────────────────────────────────────────────────
r = requests.get(f"{BASE}/api/profiles", params={
    "gender": "male", "country_id": "NG", "min_age": "25", "limit": "50"
})
check("Combined: gender=male, country_id=NG, min_age=25", r, 200, [
    ("all male",      lambda d: all(x["gender"] == "male" for x in d["data"])),
    ("all NG",        lambda d: all(x["country_id"] == "NG" for x in d["data"])),
    ("all age >= 25", lambda d: all(x["age"] >= 25 for x in d["data"])),
])

# ── 10. Sort age desc ─────────────────────────────────────────────────────
r = requests.get(f"{BASE}/api/profiles", params={"sort_by": "age", "order": "desc", "limit": "20"})
check("Sort by age desc", r, 200, [
    ("ages are descending", lambda d: all(
        d["data"][i]["age"] >= d["data"][i+1]["age"]
        for i in range(len(d["data"])-1)
    )),
])

# ── 11. Sort age asc ──────────────────────────────────────────────────────
r = requests.get(f"{BASE}/api/profiles", params={"sort_by": "age", "order": "asc", "limit": "20"})
check("Sort by age asc", r, 200, [
    ("ages are ascending", lambda d: all(
        d["data"][i]["age"] <= d["data"][i+1]["age"]
        for i in range(len(d["data"])-1)
    )),
])

# ── 12. Sort gender_probability desc ─────────────────────────────────────
r = requests.get(f"{BASE}/api/profiles", params={"sort_by": "gender_probability", "order": "desc", "limit": "20"})
check("Sort by gender_probability desc", r, 200, [
    ("probs are descending", lambda d: all(
        d["data"][i]["gender_probability"] >= d["data"][i+1]["gender_probability"]
        for i in range(len(d["data"])-1)
    )),
])

# ── 13. Pagination: different pages return different records ───────────────
r1 = requests.get(f"{BASE}/api/profiles", params={"page": "1", "limit": "10"})
r2 = requests.get(f"{BASE}/api/profiles", params={"page": "2", "limit": "10"})
d1 = r1.json()
check("Pagination: page 2 differs from page 1", r2, 200, [
    ("page field is 2",            lambda d: d.get("page") == 2),
    ("records differ from page 1", lambda d: d["data"][0]["id"] != d1["data"][0]["id"]),
])

# ── 14. Unknown query param -> 400 ────────────────────────────────────────
r = requests.get(f"{BASE}/api/profiles", params={"foo": "bar"})
check("Unknown param -> 400", r, 400, [
    ("status=error",               lambda d: d.get("status") == "error"),
    ("message mentions Invalid",   lambda d: "Invalid" in d.get("message", "")),
])

# ── 15. page=abc -> 422 ───────────────────────────────────────────────────
r = requests.get(f"{BASE}/api/profiles", params={"page": "abc"})
check("page=abc -> 422", r, 422, [
    ("status=error", lambda d: d.get("status") == "error"),
])

# ── 16. min_age=abc -> 422 ────────────────────────────────────────────────
r = requests.get(f"{BASE}/api/profiles", params={"min_age": "abc"})
check("min_age=abc -> 422", r, 422, [
    ("status=error", lambda d: d.get("status") == "error"),
])

# ── 17. min_gender_probability=abc -> 422 ──────────────────────────────────
r = requests.get(f"{BASE}/api/profiles", params={"min_gender_probability": "abc"})
check("min_gender_probability=abc -> 422", r, 422, [
    ("status=error", lambda d: d.get("status") == "error"),
])

# ── 18. gender=other -> 400 ───────────────────────────────────────────────
r = requests.get(f"{BASE}/api/profiles", params={"gender": "other"})
check("gender=other -> 400", r, 400, [
    ("status=error", lambda d: d.get("status") == "error"),
])

# ── 19. age_group=baby -> 400 ─────────────────────────────────────────────
r = requests.get(f"{BASE}/api/profiles", params={"age_group": "baby"})
check("age_group=baby -> 400", r, 400, [
    ("status=error", lambda d: d.get("status") == "error"),
])

# ── 20. sort_by=name -> 400 ───────────────────────────────────────────────
r = requests.get(f"{BASE}/api/profiles", params={"sort_by": "name"})
check("sort_by=name -> 400", r, 400, [
    ("status=error", lambda d: d.get("status") == "error"),
])

# ── 21. order=random -> 400 ───────────────────────────────────────────────
r = requests.get(f"{BASE}/api/profiles", params={"order": "random"})
check("order=random -> 400", r, 400, [
    ("status=error", lambda d: d.get("status") == "error"),
])

# ── 22. NL: 'young males from nigeria' ────────────────────────────────────
r = requests.get(f"{BASE}/api/profiles/search", params={"q": "young males from nigeria"})
check("NL: young males from nigeria", r, 200, [
    ("status=success",       lambda d: d.get("status") == "success"),
    ("all male",             lambda d: all(x["gender"] == "male" for x in d["data"])),
    ("all NG",               lambda d: all(x["country_id"] == "NG" for x in d["data"])),
    ("all ages 16-24",       lambda d: all(16 <= x["age"] <= 24 for x in d["data"])),
    ("has page/limit/total", lambda d: all(k in d for k in ("page", "limit", "total"))),
])

# ── 23. NL: 'females above 30' ────────────────────────────────────────────
r = requests.get(f"{BASE}/api/profiles/search", params={"q": "females above 30"})
check("NL: females above 30", r, 200, [
    ("all female",    lambda d: all(x["gender"] == "female" for x in d["data"])),
    ("all age >= 30", lambda d: all(x["age"] >= 30 for x in d["data"])),
])

# ── 24. NL: 'people from angola' ─────────────────────────────────────────
r = requests.get(f"{BASE}/api/profiles/search", params={"q": "people from angola"})
check("NL: people from angola", r, 200, [
    ("all AO", lambda d: all(x["country_id"] == "AO" for x in d["data"])),
])

# ── 25. NL: 'adult males from kenya' ─────────────────────────────────────
r = requests.get(f"{BASE}/api/profiles/search", params={"q": "adult males from kenya"})
check("NL: adult males from kenya", r, 200, [
    ("all male",  lambda d: all(x["gender"] == "male" for x in d["data"])),
    ("all adult", lambda d: all(x["age_group"] == "adult" for x in d["data"])),
    ("all KE",    lambda d: all(x["country_id"] == "KE" for x in d["data"])),
])

# ── 26. NL: 'male and female teenagers above 17' ──────────────────────────
r = requests.get(f"{BASE}/api/profiles/search", params={"q": "male and female teenagers above 17"})
check("NL: male and female teenagers above 17", r, 200, [
    ("all teenager",  lambda d: all(x["age_group"] == "teenager" for x in d["data"])),
    ("all age >= 17", lambda d: all(x["age"] >= 17 for x in d["data"])),
    ("both genders",  lambda d: len({x["gender"] for x in d["data"]}) > 1),
])

# ── 27. NL: uninterpretable -> 400 ────────────────────────────────────────
r = requests.get(f"{BASE}/api/profiles/search", params={"q": "hello world"})
check("NL: hello world -> unable to interpret", r, 400, [
    ("status=error",                lambda d: d.get("status") == "error"),
    ("message=Unable to interpret", lambda d: "Unable to interpret" in d.get("message", "")),
])

# ── 28. NL: missing q -> 400 ──────────────────────────────────────────────
r = requests.get(f"{BASE}/api/profiles/search")
check("NL: missing q -> 400", r, 400, [
    ("status=error", lambda d: d.get("status") == "error"),
])

# ── 29. NL: pagination ───────────────────────────────────────────────────
r = requests.get(f"{BASE}/api/profiles/search", params={"q": "females above 30", "page": "2", "limit": "5"})
check("NL search pagination (page=2, limit=5)", r, 200, [
    ("page=2",    lambda d: d.get("page") == 2),
    ("limit=5",   lambda d: d.get("limit") == 5),
    ("total > 0", lambda d: d.get("total", 0) > 0),
    ("5 records", lambda d: len(d.get("data", [])) == 5),
])

# ── 30. NL: extra keywords (senior women) ─────────────────────────────────
r = requests.get(f"{BASE}/api/profiles/search", params={"q": "senior women"})
check("NL: senior women", r, 200, [
    ("all female", lambda d: all(x["gender"] == "female" for x in d["data"])),
    ("all senior", lambda d: all(x["age_group"] == "senior" for x in d["data"])),
])

# ── 31. CORS header ───────────────────────────────────────────────────────
r = requests.get(f"{BASE}/api/profiles")
check("CORS: Access-Control-Allow-Origin: *", r, 200, [
    ("header is *", lambda d: r.headers.get("Access-Control-Allow-Origin") == "*"),
])

# ── 32. Timestamps end with Z ────────────────────────────────────────────
r = requests.get(f"{BASE}/api/profiles", params={"limit": "1"})
check("Timestamps are UTC ISO 8601 (Z suffix)", r, 200, [
    ("created_at ends with Z", lambda d: d["data"][0]["created_at"].endswith("Z")),
])

# ── 33. IDs are UUID format ───────────────────────────────────────────────
uuid_pat = _re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
r = requests.get(f"{BASE}/api/profiles", params={"limit": "5"})
check("IDs are UUID format", r, 200, [
    ("all ids match UUID pattern", lambda d: all(uuid_pat.match(x["id"]) for x in d["data"])),
])

# ── 34. 404 for unknown route ────────────────────────────────────────────
r = requests.get(f"{BASE}/api/doesnotexist")
check("404 for unknown route", r, 404, [
    ("status=error", lambda d: d.get("status") == "error"),
])

# ── 35. POST /api/profiles ────────────────────────────────────────────────
r = requests.post(f"{BASE}/api/profiles", json={
    "name": "__test_user__",
    "gender": "male",
    "gender_probability": 0.9,
    "age": 28,
    "age_group": "adult",
    "country_id": "NG",
    "country_name": "Nigeria",
    "country_probability": 0.85,
})
check("POST /api/profiles creates profile", r, 201, [
    ("status=success", lambda d: d.get("status") == "success"),
    ("id present",     lambda d: "id" in d.get("data", {})),
])

# ── Summary ───────────────────────────────────────────────────────────────
total = passed + failed
print()
print("=" * 52)
print(f"  Results: {passed}/{total} passed   {'ALL GOOD' if not failed else str(failed) + ' FAILED'}")
print("=" * 52)
sys.exit(0 if failed == 0 else 1)
