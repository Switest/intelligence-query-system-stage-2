# Stage 2 Implementation Plan — Intelligence Query Engine

## Current State

`app.py` is a single-file Flask app backed by SQLite. It has:

- `GET /api/profiles` — pagination only (no filters, no sorting, max limit is 100 not 50)
- `POST /api/profiles` — create a profile
- `GET /api/profiles/search?q=` — basic keyword matching against name/country_name/age_group (broken, not spec-compliant)
- `seed_db()` skips seeding if any rows exist (fine for first run)

---

## What Must Change

### 1. Database schema

| Change | Why |
|---|---|
| Add `UNIQUE` constraint on `name` | Spec requires it; also prevents duplicate seeds |
| Add indexes on `gender`, `age`, `age_group`, `country_id`, `created_at`, `gender_probability`, `country_probability` | Spec says no unnecessary full-table scans |
| Lower limit cap to 50 | Spec says max 50 |

**Strategy:** Drop and recreate the table inside `init_db()` using `CREATE TABLE IF NOT EXISTS`. Since the name column needs UNIQUE and it wasn't there before, we need to delete the old `profiles.db` on first run or use a migration. The safest approach for local testing: delete `profiles.db` before restarting so `init_db()` creates a fresh schema, then `seed_db()` re-seeds.

### 2. `GET /api/profiles`

Add all of:

**Filters** (all combinable with AND):
- `gender` — exact match (`male` | `female`)
- `age_group` — exact match (`child` | `teenager` | `adult` | `senior`)
- `country_id` — exact match (e.g. `NG`, `AO`)
- `min_age` — `age >= X`
- `max_age` — `age <= X`
- `min_gender_probability` — `gender_probability >= X`
- `min_country_probability` — `country_probability >= X`

**Sorting:**
- `sort_by` — allowed values: `age`, `created_at`, `gender_probability`
- `order` — `asc` | `desc` (default `asc`)

**Pagination:**
- `page` default 1, `limit` default 10, max 50

**Validation:**
- Unknown query params → 400 `{ "status": "error", "message": "Invalid query parameters" }`
- Non-integer `page`/`limit`/`min_age`/`max_age` → 422 `{ "status": "error", "message": "Invalid parameter type" }`
- Non-float `min_gender_probability`/`min_country_probability` → 422

**Response shape** (must match exactly):
```json
{
  "status": "success",
  "page": 1,
  "limit": 10,
  "total": 2026,
  "data": [ ... ]
}
```

### 3. `GET /api/profiles/search`

Full rewrite. Rule-based NL parser → extract filters → reuse the same filter/pagination query logic as `/api/profiles`.

**Pagination applies:** `page`, `limit` query params work the same way.

**Response shape:**
```json
{
  "status": "success",
  "page": 1,
  "limit": 10,
  "total": 45,
  "data": [ ... ]
}
```

---

## Natural Language Parser Design

### Approach

Pure keyword/regex matching in Python. Parse the lowercased query string in order:

#### Gender keywords
| Query contains | Filter |
|---|---|
| `female`, `females`, `woman`, `women`, `girl`, `girls` | `gender = female` |
| `male`, `males`, `man`, `men`, `boy`, `boys` | `gender = male` |
| both genders mentioned | no gender filter |

**Note:** "male" is a substring of "female" — check for `female` first before checking `male`.

#### Age-group keywords
| Query contains | Filter |
|---|---|
| `young`, `youth` | `min_age=16`, `max_age=24` (not a stored group; parsing only) |
| `teenager`, `teenagers`, `teenage`, `teen`, `teens` | `age_group = teenager` |
| `adult`, `adults` | `age_group = adult` |
| `senior`, `seniors`, `elderly`, `old` | `age_group = senior` |
| `child`, `children`, `kid`, `kids` | `age_group = child` |

#### Numeric age constraints
Use regex to extract:
- `above (\d+)` / `over (\d+)` / `older than (\d+)` → `min_age = N`
- `below (\d+)` / `under (\d+)` / `younger than (\d+)` → `max_age = N`
- `between (\d+) and (\d+)` / `aged (\d+) to (\d+)` → `min_age = A, max_age = B`

#### Country detection
After stripping gender/age keywords and prepositions (`from`, `in`, `of`), check remaining words against a country-name-to-ISO-code lookup table.

**Lookup table (key countries in dataset):**
```python
COUNTRY_MAP = {
    "nigeria": "NG", "nigerian": "NG",
    "ghana": "GH", "ghanaian": "GH",
    "kenya": "KE", "kenyan": "KE",
    "ethiopia": "ET", "ethiopian": "ET",
    "angola": "AO", "angolan": "AO",
    "benin": "BJ", "beninese": "BJ",
    "cameroon": "CM", "cameroonian": "CM",
    "senegal": "SN", "senegalese": "SN",
    "mali": "ML", "malian": "ML",
    "guinea": "GN", "guinean": "GN",
    "ivory coast": "CI", "cote d'ivoire": "CI",
    "burkina faso": "BF",
    "niger": "NE", "nigerien": "NE",
    "togo": "TG", "togolese": "TG",
    "sierra leone": "SL",
    "liberia": "LR", "liberian": "LR",
    "gambia": "GM", "gambian": "GM",
    "mauritania": "MR",
    "south africa": "ZA", "south african": "ZA",
    "tanzania": "TZ", "tanzanian": "TZ",
    "uganda": "UG", "ugandan": "UG",
    "mozambique": "MZ",
    "zambia": "ZM", "zambian": "ZM",
    "zimbabwe": "ZW", "zimbabwean": "ZW",
    "malawi": "MW", "malawian": "MW",
    "rwanda": "RW", "rwandan": "RW",
    "burundi": "BI", "burundian": "BI",
    "congo": "CG", "congolese": "CG",
    "dr congo": "CD", "drc": "CD",
    "chad": "TD", "chadian": "TD",
    "sudan": "SD", "sudanese": "SD",
    "somalia": "SO", "somali": "SO",
    "egypt": "EG", "egyptian": "EG",
    "morocco": "MA", "moroccan": "MA",
    "algeria": "DZ", "algerian": "DZ",
    "tunisia": "TN", "tunisian": "TN",
    "libya": "LY", "libyan": "LY",
    "france": "FR", "french": "FR",
    "united kingdom": "GB", "uk": "GB", "britain": "GB", "british": "GB",
    "united states": "US", "usa": "US", "american": "US",
    "canada": "CA", "canadian": "CA",
    "germany": "DE", "german": "DE",
    "china": "CN", "chinese": "CN",
    "india": "IN", "indian": "IN",
    "brazil": "BR", "brazilian": "BR",
}
```

#### "Unable to interpret" rule
If after parsing, **no filter was extracted at all**, return:
```json
{ "status": "error", "message": "Unable to interpret query" }
```

---

## Example Query Mappings

| Query | Extracted filters |
|---|---|
| `young males from nigeria` | gender=male, min_age=16, max_age=24, country_id=NG |
| `females above 30` | gender=female, min_age=30 |
| `people from angola` | country_id=AO |
| `adult males from kenya` | gender=male, age_group=adult, country_id=KE |
| `male and female teenagers above 17` | age_group=teenager, min_age=17 |
| `senior women` | gender=female, age_group=senior |
| `children under 10` | age_group=child, max_age=10 |
| `hello world` | → 400 "Unable to interpret query" |

---

## Implementation Steps

### Step 1 — Rewrite `app.py`

1. Update `init_db()`:
   - Add UNIQUE on `name`
   - Create indexes: `idx_gender`, `idx_age`, `idx_age_group`, `idx_country_id`, `idx_created_at`, `idx_gender_prob`, `idx_country_prob`

2. Rewrite `GET /api/profiles`:
   - Parse and whitelist all allowed query params (reject unknown params with 400)
   - Validate types (422 for bad types)
   - Build dynamic `WHERE` clause from filters
   - Apply `ORDER BY` from sort params (whitelist sort_by values)
   - Apply `LIMIT`/`OFFSET` with cap at 50
   - Run `COUNT(*)` with same filters for `total`

3. Rewrite `GET /api/profiles/search`:
   - Implement `parse_nl_query(q)` → returns dict of filters or `None` if unparseable
   - If `None`, return 400 "Unable to interpret query"
   - Otherwise, feed filters into the same query-building logic used by `GET /api/profiles`

4. Keep `POST /api/profiles` as-is (spec doesn't change it).

5. Add 404 handler for unknown routes.

### Step 2 — Delete old database and re-seed

```bash
rm profiles.db
python app.py
```

`init_db()` creates fresh schema with UNIQUE + indexes, then `seed_db()` seeds all 2026 profiles.

### Step 3 — Test locally

Test checklist:
- [ ] `GET /api/profiles` returns 10 records, total=2026
- [ ] `GET /api/profiles?gender=male&country_id=NG&sort_by=age&order=desc&limit=5` returns 5 male Nigerians sorted by age desc
- [ ] `GET /api/profiles?min_age=25&max_age=40` returns only ages 25-40
- [ ] `GET /api/profiles?limit=51` is capped at 50
- [ ] `GET /api/profiles?unknown_param=x` returns 400
- [ ] `GET /api/profiles?page=abc` returns 422
- [ ] `GET /api/profiles/search?q=young males from nigeria` returns results with correct filters
- [ ] `GET /api/profiles/search?q=females above 30` returns results
- [ ] `GET /api/profiles/search?q=hello world` returns "Unable to interpret query"
- [ ] `GET /api/profiles/search` (no `q`) returns 400
- [ ] CORS header `Access-Control-Allow-Origin: *` present on all responses

### Step 4 — Update README

Cover:
1. Natural language parsing approach (keywords, mappings, logic)
2. Limitations (parser edge cases, what's not supported)

### Step 5 — Deploy to Railway

- Push to GitHub
- Railway auto-deploys from main branch
- Set `PORT` env var if needed (Railway injects it automatically)
- Confirm DB is seeded (Railway uses ephemeral filesystem — consider if SQLite is appropriate or if Postgres is needed)

---

## Railway / Persistence Note

Railway's filesystem is **ephemeral** — SQLite data is lost on redeploy. For production, switch to **PostgreSQL** (Railway provides a free Postgres addon). The code changes are minimal: swap `sqlite3` for `psycopg2`, use `%s` placeholders, and read `DATABASE_URL` from env.

**Decision:** Use PostgreSQL on Railway, SQLite locally. Use an env var `DATABASE_URL` to switch — if set, use Postgres; otherwise fall back to SQLite.

---

## File Changes Summary

| File | Action |
|---|---|
| `app.py` | Full rewrite (schema, endpoints, NL parser) |
| `README.md` | Update with NL parsing docs |
| `profiles.db` | Delete before first run (schema changed) |
| `requirements.txt` | Add `psycopg2-binary` for Railway Postgres |
