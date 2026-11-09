import json, sqlite3, time

DB_PATH = "smartstay.db"

def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS profiles(
            session_id TEXT PRIMARY KEY, consent INTEGER DEFAULT 0,
            prefs TEXT DEFAULT '[]', language TEXT DEFAULT 'en', consent_at REAL);
        CREATE TABLE IF NOT EXISTS requests(
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, kind TEXT,
            detail TEXT, status TEXT DEFAULT 'new', created REAL);
        CREATE TABLE IF NOT EXISTS logs(
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, intent TEXT,
            user_msg TEXT, bot_msg TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS feedback(
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, rating INTEGER, created REAL);
        """)

def get_profile(sid):
    with conn() as c:
        r = c.execute("SELECT * FROM profiles WHERE session_id=?", (sid,)).fetchone()
    if not r:
        return {"consent": False, "prefs": [], "language": "en"}
    return {"consent": bool(r["consent"]), "prefs": json.loads(r["prefs"]), "language": r["language"]}

def set_consent(sid, consent):
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO profiles(session_id) VALUES(?)", (sid,))
        if consent:
            c.execute("UPDATE profiles SET consent=1, consent_at=? WHERE session_id=?", (time.time(), sid))
        else:  # withdrawing consent deletes stored preferences
            c.execute("UPDATE profiles SET consent=0, prefs='[]' WHERE session_id=?", (sid,))

def add_prefs(sid, new):
    p = get_profile(sid)
    if not p["consent"]:
        return  # never store without consent
    prefs = sorted(set(p["prefs"]) | set(new))
    with conn() as c:
        c.execute("UPDATE profiles SET prefs=? WHERE session_id=?", (json.dumps(prefs), sid))

def add_request(sid, kind, detail):
    with conn() as c:
        cur = c.execute("INSERT INTO requests(session_id,kind,detail,created) VALUES(?,?,?,?)",
                        (sid, kind, detail, time.time()))
        return cur.lastrowid

def list_requests():
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM requests ORDER BY id DESC LIMIT 100")]

def set_request_status(rid, status):
    with conn() as c:
        c.execute("UPDATE requests SET status=? WHERE id=?", (status, rid))

def log_chat(sid, intent, user_msg, bot_msg):
    with conn() as c:  # user_msg must already be masked
        c.execute("INSERT INTO logs(session_id,intent,user_msg,bot_msg,created) VALUES(?,?,?,?,?)",
                  (sid, intent, user_msg, bot_msg, time.time()))

def add_feedback(sid, rating):
    with conn() as c:
        c.execute("INSERT INTO feedback(session_id,rating,created) VALUES(?,?,?)", (sid, rating, time.time()))

def stats():
    with conn() as c:
        n = c.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
        fb = c.execute("SELECT AVG(rating), COUNT(*) FROM feedback").fetchone()
    return {"messages": n, "avg_rating": round(fb[0], 2) if fb[0] else None, "ratings": fb[1]}

# ---------- Requirements research (surveys + interviews) ----------
def init_research():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS survey_responses(
            id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, answers TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS interviews(
            id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, participant_code TEXT,
            functional_needs TEXT, non_functional_needs TEXT, notes TEXT, created REAL);
        """)

def add_survey(role, answers):
    init_research()
    with conn() as c:
        cur = c.execute("INSERT INTO survey_responses(role,answers,created) VALUES(?,?,?)",
                        (role, json.dumps(answers), time.time()))
        return cur.lastrowid

def add_interview(role, code, functional, non_functional, notes):
    init_research()
    with conn() as c:
        cur = c.execute("INSERT INTO interviews(role,participant_code,functional_needs,non_functional_needs,notes,created) VALUES(?,?,?,?,?,?)",
                        (role, code, functional, non_functional, notes, time.time()))
        return cur.lastrowid

def list_surveys():
    init_research()
    with conn() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM survey_responses ORDER BY id")]
    for r in rows:
        r["answers"] = json.loads(r["answers"])
    return rows

def list_interviews():
    init_research()
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM interviews ORDER BY id")]
