import os
import sqlite3
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
from uuid6 import uuid7
from datetime import datetime, timezone

app = Flask(__name__)
CORS(app)
DB_PATH = 'profiles.db'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS profiles (
            id TEXT PRIMARY KEY,
            name TEXT,
            gender TEXT,
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

@app.route('/api/profiles', methods=['GET', 'POST'])
def handle_profiles():
    conn = get_db()
    
    if request.method == 'POST':
        p = request.json
        new_id = str(uuid7())
        try:
            conn.execute('''
                INSERT INTO profiles (id, name, gender, gender_probability, age, age_group, country_id, country_name, country_probability, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (new_id, p.get('name'), p.get('gender'), p.get('gender_probability'), 
                  p.get('age'), p.get('age_group'), p.get('country_id'), 
                  p.get('country_name'), p.get('country_probability'), 
                  datetime.now(timezone.utc).isoformat()))
            conn.commit()
            return jsonify({"status": "success", "data": {"id": new_id, **p}}), 201
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 400

    # GET with Pagination
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
        if limit > 100: limit = 100 # Max cap behavior
        offset = (page - 1) * limit

        total = conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0]
        rows = conn.execute("SELECT * FROM profiles LIMIT ? OFFSET ?", (limit, offset)).fetchall()
        
        return jsonify({
            "status": "success",
            "data": [dict(row) for row in rows],
            "page": page,
            "limit": limit,
            "total": total
        }), 200
    finally:
        conn.close()

@app.route('/api/profiles/search', methods=['GET'])
def search_profiles():
    query = request.args.get('q', '').lower()
    if not query:
        return jsonify({"status": "error", "message": "Query parameter 'q' is required"}), 400

    conn = get_db()
    
    sql = "SELECT * FROM profiles WHERE 1=1"
    params = []

    if 'female' in query:
        sql += " AND gender = 'female'"
    elif 'male' in query:
        sql += " AND gender = 'male'"
    
    # Extract potential country/name keywords (basic split)
    keywords = query.replace('from', '').replace('in', '').split()
    for word in keywords:
        if word not in ['male', 'female', 'profiles', 'people']:
            sql += " AND (country_name LIKE ? OR name LIKE ? OR age_group LIKE ?)"
            params.extend([f'%{word}%', f'%{word}%', f'%{word}%'])

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    return jsonify({
        "status": "success",
        "data": [dict(row) for row in rows],
        "count": len(rows)
    }), 200

def seed_db():
    if not os.path.exists('profiles.json'): return
    conn = get_db()
    if conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0] > 0:
        conn.close()
        return
    with open('profiles.json', 'r') as f:
        raw = json.load(f)
        data = raw.get('profiles', []) if isinstance(raw, dict) else raw
        for p in data:
            conn.execute('INSERT OR IGNORE INTO profiles VALUES (?,?,?,?,?,?,?,?,?,?)',
                (str(uuid7()), p.get('name'), p.get('gender'), p.get('gender_probability'),
                 p.get('age'), p.get('age_group'), p.get('country_id'), p.get('country_name'),
                 p.get('country_probability'), datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    seed_db()

    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
