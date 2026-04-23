# Intelligence Query System — Stage 2

A Flask REST API for querying 2026 demographic intelligence profiles with advanced filtering, sorting, pagination, and natural language search.

## Tech Stack

- **Backend:** Python 3 / Flask
- **Database:** SQLite (local) · PostgreSQL (Railway — via `DATABASE_URL` env var)
- **ID Generation:** UUID v7 (time-ordered)
- **Deployment:** Railway

## Setup

```bash
pip install -r requirements.txt
python app.py          # creates DB, seeds 2026 profiles, starts on :5000
```

The database is initialised and seeded automatically on startup. Re-running never creates duplicates (`INSERT OR IGNORE` / `ON CONFLICT DO NOTHING` keyed on the unique `name` column).

---

## API Endpoints

### `GET /api/profiles`

Returns profiles with optional filtering, sorting, and pagination.

**Filters**

| Parameter | Type | Description |
|---|---|---|
| `gender` | string | `male` or `female` |
| `age_group` | string | `child`, `teenager`, `adult`, `senior` |
| `country_id` | string | ISO 3166-1 alpha-2 (e.g. `NG`, `KE`) |
| `min_age` | integer | Minimum age (inclusive) |
| `max_age` | integer | Maximum age (inclusive) |
| `min_gender_probability` | float | Minimum gender confidence score |
| `min_country_probability` | float | Minimum country confidence score |

**Sorting**

| Parameter | Values | Default |
|---|---|---|
| `sort_by` | `age`, `created_at`, `gender_probability` | `created_at` |
| `order` | `asc`, `desc` | `asc` |

**Pagination**

| Parameter | Default | Max |
|---|---|---|
| `page` | 1 | — |
| `limit` | 10 | 50 |

**Example**

```
GET /api/profiles?gender=male&country_id=NG&min_age=25&sort_by=age&order=desc&page=1&limit=10
```

```json
{
  "status": "success",
  "page": 1,
  "limit": 10,
  "total": 60,
  "data": [{ "id": "...", "name": "Tunde Barro", "gender": "male", ... }]
}
```

---

### `GET /api/profiles/search?q=<query>`

Natural language query endpoint. Converts plain-English phrases into structured filters and returns paginated results.

`page` and `limit` query params apply here too.

**Example**

```
GET /api/profiles/search?q=young males from nigeria&page=1&limit=10
```

---

## Natural Language Parsing Approach

The parser is fully rule-based — no AI or LLMs. It operates on the lowercased query string in five stages:

### 1. Gender detection

Checks the query's word set against two keyword lists:

| Keywords | Maps to |
|---|---|
| `female`, `females`, `woman`, `women`, `girl`, `girls` | `gender = female` |
| `male`, `males`, `man`, `men`, `boy`, `boys` | `gender = male` |

If both sets are matched (e.g. "male and female"), no gender filter is applied.
`female` is checked before `male` so "female" is never mis-matched as containing "male".

### 2. Age-group / "young" detection

`young` and `youth` are special keywords that map to a numeric range (`min_age=16, max_age=24`) rather than a stored age group. All other age-group terms are checked word-by-word:

| Keywords | Maps to |
|---|---|
| `young`, `youth` | `min_age=16`, `max_age=24` |
| `teenager`, `teenagers`, `teenage`, `teen`, `teens` | `age_group = teenager` |
| `adult`, `adults` | `age_group = adult` |
| `senior`, `seniors`, `elderly` | `age_group = senior` |
| `child`, `children`, `kid`, `kids` | `age_group = child` |

### 3. Numeric age constraints (regex)

Applied on top of any age-group/young keywords already set:

| Pattern | Effect |
|---|---|
| `above N` / `over N` / `older than N` | `min_age = N` |
| `below N` / `under N` / `younger than N` | `max_age = N` |
| `between N and M` | `min_age = N`, `max_age = M` |
| `age N to M` / `aged N to M` | `min_age = N`, `max_age = M` |

### 4. Country detection

Multi-word country names (e.g. "south africa", "burkina faso") are matched first (longest to shortest) against the full query string. Remaining unmatched single words are then checked against a country dictionary of ~130 entries covering all 64 countries in the dataset plus common adjective forms (e.g. "nigerian" → `NG`, "kenyan" → `KE`).

Countries supported include all African nations present in the dataset, plus Australia, Brazil, Canada, China, France, Germany, India, Japan, UK, and USA.

### 5. Failure case

If no filter at all was extracted from the query, the endpoint returns:

```json
{ "status": "error", "message": "Unable to interpret query" }
```

### Example mappings

| Query | Extracted filters |
|---|---|
| `young males from nigeria` | `gender=male, min_age=16, max_age=24, country_id=NG` |
| `females above 30` | `gender=female, min_age=30` |
| `people from angola` | `country_id=AO` |
| `adult males from kenya` | `gender=male, age_group=adult, country_id=KE` |
| `male and female teenagers above 17` | `age_group=teenager, min_age=17` |
| `senior women` | `gender=female, age_group=senior` |
| `children under 10` | `age_group=child, max_age=10` |

---

## Limitations

- **No typo tolerance.** Keywords must be spelled exactly. "Nigerria" or "femal" will not match.
- **No OR logic.** All extracted filters are combined with AND. "males or females" is treated as both genders present, so no gender filter is applied.
- **No negation.** "not from nigeria" or "excluding adults" is not supported.
- **"young" is not a stored age group.** It maps to `min_age=16, max_age=24` for query purposes only; it does not filter by the `age_group` column.
- **Ambiguous country names.** Plain "guinea" maps to Guinea (GN); to target Guinea-Bissau (GW) or Equatorial Guinea (GQ), use the full name. Plain "congo" maps to Republic of the Congo (CG); use "dr congo" or "drc" for CD.
- **No compound country + age logic.** "Nigerians aged 20" works, but "20-year-old Nigerians" does not — numeric age extraction requires the keywords `above/below/between/aged`.
- **No name-based search.** The NL endpoint only filters by gender, age group, age range, and country. Searching by a person's name is not supported.
- **No relative time expressions.** "recently added" or "joined last month" cannot be interpreted.

---

## Error Responses

All errors follow this structure:

```json
{ "status": "error", "message": "<description>" }
```

| Status | Condition |
|---|---|
| 400 | Missing required param, unknown query param, or uninterpretable NL query |
| 422 | Wrong type for a numeric parameter (e.g. `page=abc`) |
| 404 | Unknown route |
| 500 | Unhandled server error |
