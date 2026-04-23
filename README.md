# Intelligence Query System - Stage 2

A Flask-based API that manages 2026 intelligence profiles with natural language search capabilities.

## Tech Stack
- **Backend:** Python (Flask)
- **Database:** SQLite
- **ID Generation:** UUID v7 (Time-ordered)
- **Deployment:** [Insert your Render or Railway link here]

## Setup Instructions
1. Install dependencies: `pip install -r requirements.txt`
2. Run the application: `python app.py`
3. The database will automatically seed from `profiles.json` on the first run.

## API Endpoints
- `GET /api/profiles`: Fetch all profiles (supports pagination and filtering).
- `GET /api/profiles/search?q=query`: Natural language search (e.g., "males from nigeria").
## Natural Language Parsing Approach
My implementation uses a **Deterministic Rule-Based Parser**. It utilizes
Python's `re` (Regular Expression) module to tokenize the query string and
identify key intelligence markers:
- **Gender Tokens**: Maps 'male', 'man', 'boy' to 'male' and 'female',
'woman', 'girl' to 'female'.
- **Age Mapping**: Detects 'young' and explicitly maps it to a range of 16-24.
- **Numeric Logic**: Scans for patterns like 'above [X]' or 'older than [X]'
and converts them into minimum age constraints (X+1).
- **Geographic Mapping**: Matches country names (e.g., 'Nigeria') to ISO-3166
codes ('NG').
## Limitations
- **Typos**: The parser requires exact spelling of keywords.
- **Complexity**: It does not support 'OR' logic (e.g., 'males or females').
It defaults to 'AND'.
- **Negation**: It cannot interpret negative queries (e.g., 'not from
Nigeria').