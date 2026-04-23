import os
import json
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
from uuid6 import uuid7
from datetime import datetime, timezone

DATABASE_URL = os.environ.get('DATABASE_URL')
USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras
    PH = '%s'
else:
    import sqlite3
    PH = '?'

app = Flask(__name__)
CORS(app)

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_db():
    if USE_POSTGRES:
        return psycopg2.connect(DATABASE_URL)
    conn = sqlite3.connect('profiles.db')
    conn.row_factory = sqlite3.Row
    return conn

def db_execute(conn, sql, params=()):
    if USE_POSTGRES:
        cur = conn.cursor()
        cur.execute(sql, list(params))
    else:
        conn.execute(sql, params)

def db_fetchall(conn, sql, params=()):
    if USE_POSTGRES:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, list(params))
        return [dict(r) for r in cur.fetchall()]
    return [dict(r) for r in conn.execute(sql, params).fetchall()]

def db_scalar(conn, sql, params=()):
    if USE_POSTGRES:
        cur = conn.cursor()
        cur.execute(sql, list(params))
        row = cur.fetchone()
        return row[0] if row else 0
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else 0

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def init_db():
    conn = get_db()
    try:
        db_execute(conn, '''
            CREATE TABLE IF NOT EXISTS profiles (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE,
                gender TEXT,
                gender_probability FLOAT,
                age INTEGER,
                age_group TEXT,
                country_id TEXT,
                country_name TEXT,
                country_probability FLOAT,
                created_at TEXT
            )
        ''')
        for idx, col in [
            ('idx_gender', 'gender'),
            ('idx_age', 'age'),
            ('idx_age_group', 'age_group'),
            ('idx_country_id', 'country_id'),
            ('idx_created_at', 'created_at'),
            ('idx_gender_prob', 'gender_probability'),
            ('idx_country_prob', 'country_probability'),
        ]:
            db_execute(conn, f'CREATE INDEX IF NOT EXISTS {idx} ON profiles ({col})')
        conn.commit()
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------

def seed_db():
    if not os.path.exists('profiles.json'):
        return
    conn = get_db()
    try:
        if db_scalar(conn, 'SELECT COUNT(*) FROM profiles') > 0:
            return
        with open('profiles.json', encoding='utf-8') as f:
            raw = json.load(f)
        data = raw.get('profiles', raw) if isinstance(raw, dict) else raw
        now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        for p in data:
            row = (
                str(uuid7()), p.get('name'), p.get('gender'),
                p.get('gender_probability'), p.get('age'), p.get('age_group'),
                p.get('country_id'), p.get('country_name'),
                p.get('country_probability'), now,
            )
            if USE_POSTGRES:
                db_execute(conn, '''
                    INSERT INTO profiles
                        (id, name, gender, gender_probability, age, age_group,
                         country_id, country_name, country_probability, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (name) DO NOTHING
                ''', row)
            else:
                conn.execute('''
                    INSERT OR IGNORE INTO profiles
                        (id, name, gender, gender_probability, age, age_group,
                         country_id, country_name, country_probability, created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                ''', row)
        conn.commit()
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# Natural language parser
# ---------------------------------------------------------------------------

COUNTRY_MAP = {
    # Africa
    "angola": "AO",       "angolan": "AO",
    "algeria": "DZ",      "algerian": "DZ",
    "benin": "BJ",        "beninese": "BJ",
    "botswana": "BW",     "batswana": "BW",
    "burkina faso": "BF", "burkinabe": "BF",
    "burundi": "BI",      "burundian": "BI",
    "cameroon": "CM",     "cameroonian": "CM",
    "cape verde": "CV",   "cabo verde": "CV",
    "central african republic": "CF",
    "chad": "TD",         "chadian": "TD",
    "comoros": "KM",      "comorian": "KM",
    "congo": "CG",        "congolese": "CG",
    "republic of the congo": "CG",
    "dr congo": "CD",     "democratic republic of congo": "CD",  "drc": "CD",
    "djibouti": "DJ",     "djiboutian": "DJ",
    "egypt": "EG",        "egyptian": "EG",
    "equatorial guinea": "GQ",
    "eritrea": "ER",      "eritrean": "ER",
    "eswatini": "SZ",     "swaziland": "SZ",
    "ethiopia": "ET",     "ethiopian": "ET",
    "gabon": "GA",        "gabonese": "GA",
    "gambia": "GM",       "gambian": "GM",
    "ghana": "GH",        "ghanaian": "GH",
    "guinea": "GN",       "guinean": "GN",
    "guinea bissau": "GW","guinea-bissau": "GW",
    "kenya": "KE",        "kenyan": "KE",
    "lesotho": "LS",      "basotho": "LS",
    "liberia": "LR",      "liberian": "LR",
    "libya": "LY",        "libyan": "LY",
    "madagascar": "MG",   "malagasy": "MG",
    "malawi": "MW",       "malawian": "MW",
    "mali": "ML",         "malian": "ML",
    "mauritania": "MR",   "mauritanian": "MR",
    "mauritius": "MU",    "mauritian": "MU",
    "morocco": "MA",      "moroccan": "MA",
    "mozambique": "MZ",   "mozambican": "MZ",
    "namibia": "NA",      "namibian": "NA",
    "niger": "NE",        "nigerien": "NE",
    "nigeria": "NG",      "nigerian": "NG",
    "rwanda": "RW",       "rwandan": "RW",
    "senegal": "SN",      "senegalese": "SN",
    "seychelles": "SC",   "seychellois": "SC",
    "sierra leone": "SL", "sierra leonean": "SL",
    "somalia": "SO",      "somali": "SO",  "somalian": "SO",
    "south africa": "ZA", "south african": "ZA",
    "south sudan": "SS",  "south sudanese": "SS",
    "sudan": "SD",        "sudanese": "SD",
    "tanzania": "TZ",     "tanzanian": "TZ",
    "togo": "TG",         "togolese": "TG",
    "tunisia": "TN",      "tunisian": "TN",
    "uganda": "UG",       "ugandan": "UG",
    "western sahara": "EH",
    "zambia": "ZM",       "zambian": "ZM",
    "zimbabwe": "ZW",     "zimbabwean": "ZW",
    # Rest of world
    "australia": "AU",    "australian": "AU",
    "brazil": "BR",       "brazilian": "BR",
    "canada": "CA",       "canadian": "CA",
    "china": "CN",        "chinese": "CN",
    "france": "FR",       "french": "FR",
    "germany": "DE",      "german": "DE",
    "india": "IN",        "indian": "IN",
    "japan": "JP",        "japanese": "JP",
    "united kingdom": "GB", "uk": "GB", "britain": "GB", "british": "GB",
    "united states": "US", "usa": "US", "america": "US", "american": "US",
}

_MULTI_WORD_COUNTRIES = sorted(
    ((k, v) for k, v in COUNTRY_MAP.items() if ' ' in k),
    key=lambda x: -len(x[0])
)
_SINGLE_WORD_COUNTRIES = {k: v for k, v in COUNTRY_MAP.items() if ' ' not in k}

FEMALE_WORDS = {'female', 'females', 'woman', 'women', 'girl', 'girls'}
MALE_WORDS   = {'male', 'males', 'man', 'men', 'boy', 'boys'}

AGE_GROUP_MAP = {
    'teenager': {'teenager', 'teenagers', 'teenage', 'teen', 'teens'},
    'adult':    {'adult', 'adults'},
    'senior':   {'senior', 'seniors', 'elderly'},
    'child':    {'child', 'children', 'kid', 'kids'},
}

def parse_nl_query(q):
    ql = q.lower().strip()
    words = set(re.findall(r'\b\w+\b', ql))
    filters = {}

    # Gender
    has_female = bool(words & FEMALE_WORDS)
    has_male   = bool(words & MALE_WORDS)
    if has_female and not has_male:
        filters['gender'] = 'female'
    elif has_male and not has_female:
        filters['gender'] = 'male'

    # Age: "young/youth" overrides age_group keywords
    if words & {'young', 'youth'}:
        filters['min_age'] = 16
        filters['max_age'] = 24
    else:
        for group, synonyms in AGE_GROUP_MAP.items():
            if words & synonyms:
                filters['age_group'] = group
                break

    # Numeric age bounds (applied on top of age-group / young keywords)
    m = re.search(r'\b(?:above|over|older\s+than)\s+(\d+)', ql)
    if m:
        filters['min_age'] = int(m.group(1))

    m = re.search(r'\b(?:below|under|younger\s+than)\s+(\d+)', ql)
    if m:
        filters['max_age'] = int(m.group(1))

    m = re.search(r'\bbetween\s+(\d+)\s+and\s+(\d+)', ql)
    if m:
        filters['min_age'] = int(m.group(1))
        filters['max_age'] = int(m.group(2))

    m = re.search(r'\baged?\s+(\d+)\s+to\s+(\d+)', ql)
    if m:
        filters['min_age'] = int(m.group(1))
        filters['max_age'] = int(m.group(2))

    # Country — try multi-word first, then single-word
    country_id = None
    for name, iso in _MULTI_WORD_COUNTRIES:
        if name in ql:
            country_id = iso
            break
    if not country_id:
        for word in words:
            if word in _SINGLE_WORD_COUNTRIES:
                country_id = _SINGLE_WORD_COUNTRIES[word]
                break
    if country_id:
        filters['country_id'] = country_id

    return filters if filters else None

# ---------------------------------------------------------------------------
# Validation constants
# ---------------------------------------------------------------------------

ALLOWED_PROFILE_PARAMS = {
    'gender', 'age_group', 'country_id',
    'min_age', 'max_age',
    'min_gender_probability', 'min_country_probability',
    'sort_by', 'order', 'page', 'limit',
}
VALID_SORT_BY    = {'age', 'created_at', 'gender_probability'}
VALID_ORDER      = {'asc', 'desc'}
VALID_GENDERS    = {'male', 'female'}
VALID_AGE_GROUPS = {'child', 'teenager', 'adult', 'senior'}

# ---------------------------------------------------------------------------
# Shared query builder
# ---------------------------------------------------------------------------

def run_profile_query(where_clauses, params, sort_by, order, page, limit):
    where_sql = ('WHERE ' + ' AND '.join(where_clauses)) if where_clauses else ''
    order_sql = f'ORDER BY {sort_by} {order.upper()}'
    conn = get_db()
    try:
        total = db_scalar(conn, f'SELECT COUNT(*) FROM profiles {where_sql}', params)
        rows  = db_fetchall(
            conn,
            f'SELECT * FROM profiles {where_sql} {order_sql} LIMIT {PH} OFFSET {PH}',
            params + [limit, (page - 1) * limit],
        )
        return jsonify({
            'status': 'success',
            'page': page,
            'limit': limit,
            'total': total,
            'data': rows,
        }), 200
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/api/profiles', methods=['GET', 'POST'])
def handle_profiles():
    if request.method == 'POST':
        return create_profile()
    return get_profiles()


def create_profile():
    p = request.get_json(silent=True)
    if not p:
        return jsonify({'status': 'error', 'message': 'Request body is required'}), 400
    conn = get_db()
    try:
        new_id  = str(uuid7())
        created = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        db_execute(conn, f'''
            INSERT INTO profiles
                (id, name, gender, gender_probability, age, age_group,
                 country_id, country_name, country_probability, created_at)
            VALUES ({PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH},{PH})
        ''', (
            new_id, p.get('name'), p.get('gender'), p.get('gender_probability'),
            p.get('age'), p.get('age_group'), p.get('country_id'),
            p.get('country_name'), p.get('country_probability'), created,
        ))
        conn.commit()
        return jsonify({'status': 'success', 'data': {'id': new_id, 'created_at': created, **p}}), 201
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400
    finally:
        conn.close()


def get_profiles():
    # Reject unknown params
    unknown = set(request.args.keys()) - ALLOWED_PROFILE_PARAMS
    if unknown:
        return jsonify({'status': 'error', 'message': 'Invalid query parameters'}), 400

    # Parse integer params
    try:
        page  = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Invalid parameter type'}), 422

    try:
        min_age = int(request.args['min_age']) if 'min_age' in request.args else None
        max_age = int(request.args['max_age']) if 'max_age' in request.args else None
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Invalid parameter type'}), 422

    # Parse float params
    try:
        min_gender_prob  = float(request.args['min_gender_probability'])  if 'min_gender_probability'  in request.args else None
        min_country_prob = float(request.args['min_country_probability']) if 'min_country_probability' in request.args else None
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Invalid parameter type'}), 422

    # Validate enum params
    gender    = request.args.get('gender')
    age_group = request.args.get('age_group')
    sort_by   = request.args.get('sort_by', 'created_at')
    order     = request.args.get('order', 'asc').lower()

    if gender and gender not in VALID_GENDERS:
        return jsonify({'status': 'error', 'message': 'Invalid query parameters'}), 400
    if age_group and age_group not in VALID_AGE_GROUPS:
        return jsonify({'status': 'error', 'message': 'Invalid query parameters'}), 400
    if sort_by not in VALID_SORT_BY:
        return jsonify({'status': 'error', 'message': 'Invalid query parameters'}), 400
    if order not in VALID_ORDER:
        return jsonify({'status': 'error', 'message': 'Invalid query parameters'}), 400

    country_id = request.args.get('country_id')
    page       = max(1, page)
    limit      = max(1, min(limit, 50))

    # Build WHERE
    where_clauses, params = [], []

    if gender:
        where_clauses.append(f'gender = {PH}'); params.append(gender)
    if age_group:
        where_clauses.append(f'age_group = {PH}'); params.append(age_group)
    if country_id:
        where_clauses.append(f'country_id = {PH}'); params.append(country_id)
    if min_age is not None:
        where_clauses.append(f'age >= {PH}'); params.append(min_age)
    if max_age is not None:
        where_clauses.append(f'age <= {PH}'); params.append(max_age)
    if min_gender_prob is not None:
        where_clauses.append(f'gender_probability >= {PH}'); params.append(min_gender_prob)
    if min_country_prob is not None:
        where_clauses.append(f'country_probability >= {PH}'); params.append(min_country_prob)

    return run_profile_query(where_clauses, params, sort_by, order, page, limit)


@app.route('/api/profiles/search', methods=['GET'])
def search_profiles():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({'status': 'error', 'message': "Query parameter 'q' is required"}), 400

    filters = parse_nl_query(q)
    if filters is None:
        return jsonify({'status': 'error', 'message': 'Unable to interpret query'}), 400

    try:
        page  = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Invalid parameter type'}), 422

    page  = max(1, page)
    limit = max(1, min(limit, 50))

    where_clauses, params = [], []

    if 'gender' in filters:
        where_clauses.append(f'gender = {PH}'); params.append(filters['gender'])
    if 'age_group' in filters:
        where_clauses.append(f'age_group = {PH}'); params.append(filters['age_group'])
    if 'country_id' in filters:
        where_clauses.append(f'country_id = {PH}'); params.append(filters['country_id'])
    if 'min_age' in filters:
        where_clauses.append(f'age >= {PH}'); params.append(filters['min_age'])
    if 'max_age' in filters:
        where_clauses.append(f'age <= {PH}'); params.append(filters['max_age'])

    return run_profile_query(where_clauses, params, 'created_at', 'asc', page, limit)


@app.errorhandler(404)
def not_found(_e):
    return jsonify({'status': 'error', 'message': 'Not found'}), 404

@app.errorhandler(500)
def server_error(_e):
    return jsonify({'status': 'error', 'message': 'Internal server error'}), 500

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

init_db()
seed_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
