import os
import re
import sqlite3
import json
import time
from datetime import datetime, timezone
from flask import Flask, request, jsonify
from flask_cors import CORS
from uuid6 import uuid7

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

DATABASE = 'profiles.db'

# --- DATABASE LOGIC ---
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS profiles (
            id TEXT PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            gender TEXT NOT NULL,
            gender_probability REAL,
            age INTEGER,
            age_group TEXT,
            country_id TEXT,
            country_name TEXT,
            country_probability REAL,
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

# --- NATURAL LANGUAGE PARSER ---
def parse_nl_query(q):
    q = q.lower()
    filters = {}
    
    # Identity Mapping
    if re.search(r'\b(male|males|man|men|boy)\b', q):
        filters['gender'] = 'male'
    elif re.search(r'\b(female|females|woman|women|girl)\b', q):
        filters['gender'] = 'female'

    # Age Groups
    for group in ['child', 'teenager', 'adult', 'senior']:
        if group in q:
            filters['age_group'] = group

    # "Young" mapping (16-24)
    if 'young' in q:
        filters['min_age'] = 16
        filters['max_age'] = 24

    # Above/Over logic
    above_match = re.search(r'(above|over|older than)\s+(\d+)', q)
    if above_match:
        filters['min_age'] = int(above_match.group(2)) + 1

    # Country mapping (Common examples, add more if needed)
    countries = {"nigeria": "NG", "kenya": "KE", "ghana": "GH", "benin": "BJ"}
    for name, code in countries.items():
        if name in q:
            filters['country_id'] = code

    return filters if filters else None

# --- QUERY ENGINE ---
def execute_query_engine(filters):
    try:
        page = int(filters.get('page', 1))
        limit = int(filters.get('limit', 10))
        if limit > 50 or limit < 1 or page < 1:
            return {"status": "error", "message": "Invalid query parameters"}, 422
    except (ValueError, TypeError):
        return {"status": "error", "message": "Invalid query parameters"}, 422

    query = "SELECT * FROM profiles WHERE 1=1"
    count_query = "SELECT COUNT(*) FROM profiles WHERE 1=1"
    params = []

    # Mapping logic
    map_dict = {
        'gender': ' AND gender = ?',
        'age_group': ' AND age_group = ?',
        'country_id': ' AND country_id = ?',
        'min_age': ' AND age >= ?',
        'max_age': ' AND age <= ?'
    }

    for key, sql in map_dict.items():
        if key in filters and filters[key]:
            query += sql
            count_query += sql
            params.append(filters[key])

    # Sorting
    sort_by = filters.get('sort_by', 'created_at')
    order = filters.get('order', 'desc').upper()
    if sort_by not in ['age', 'created_at', 'gender_probability']: sort_by = 'created_at'
    if order not in ['ASC', 'DESC']: order = 'DESC'
    
    query += f" ORDER BY {sort_by} {order} LIMIT ? OFFSET ?"
    
    conn = get_db()
    total = conn.execute(count_query, params).fetchone()[0]
    cursor = conn.execute(query, params + [limit, (page-1)*limit])
    
    # Convert rows to dicts manually to avoid 500 errors
    results = []
    for row in cursor.fetchall():
        results.append(dict(row))
    conn.close()

    return {
        "status": "success",
        "page": page,
        "limit": limit,
        "total": total,
        "data": results
    }, 200

# --- ROUTES ---

@app.route('/api/profiles', methods=['GET'])
def get_profiles():
    res, code = execute_query_engine(request.args.to_dict())
    return jsonify(res), code

@app.route('/api/profiles/search', methods=['GET'])
def search_profiles():
    q = request.args.get('q')
    if not q:
        return jsonify({"status": "error", "message": "Missing parameter"}), 400
    
    nl_filters = parse_nl_query(q)
    if not nl_filters:
        return jsonify({"status": "error", "message": "Unable to interpret query"}), 404
    
    # Combine NL filters with URL params (like page/limit)
    combined = {**nl_filters, **request.args.to_dict()}
    res, code = execute_query_engine(combined)
    return jsonify(res), code

# --- SEEDING LOGIC ---
def seed_db():
    if not os.path.exists('profiles.json'):
        print("CRITICAL: profiles.json not found!")
        return
    
    conn = get_db()
    # Check if already seeded to avoid duplicates
    count = conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0]
    if count > 0:
        conn.close()
        return

    with open('profiles.json', 'r') as f:
        raw_data = json.load(f)
    
    # Extract the list from the "profiles" key
    # If the JSON is just a list, it uses the whole thing.
    if isinstance(raw_data, dict):
        data = raw_data.get('profiles', [])
    else:
        data = raw_data
        
    print(f"Seeding {len(data)} profiles...")
    
    for p in data:
        # This prevents the 'str' object error
        if not isinstance(p, dict):
            print(f"Skipping invalid record: {p}")
            continue
            
        try:
            conn.execute('''
                INSERT OR IGNORE INTO profiles 
                (id, name, gender, gender_probability, age, age_group, country_id, country_name, country_probability, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                str(uuid7()), 
                p.get('name'), 
                p.get('gender'), 
                p.get('gender_probability'), 
                p.get('age'), 
                p.get('age_group'), 
                p.get('country_id'), 
                p.get('country_name'), 
                p.get('country_probability'), 
                datetime.now(timezone.utc).isoformat()
            ))
        except Exception as e:
            print(f"Error seeding record: {e}")
            continue
            
    conn.commit()
    conn.close()
    print("Seeding Complete!")

if __name__ == '__main__':
    init_db()
    seed_db()
    app.run(host='0.0.0.0', port=5000)
