import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, Header, HTTPException
import csv, io
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, guardrails as g, rag, llm
from .privacy import mask_pii

app = FastAPI(title="SmartStay AI")
STATIC = Path(__file__).parent.parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")
db.init_db()

class ChatIn(BaseModel):
    session_id: str
    message: str

class ConsentIn(BaseModel):
    session_id: str
    consent: bool

class FeedbackIn(BaseModel):
    session_id: str
    rating: int

def staff_only(token):
    if token != os.getenv("STAFF_TOKEN", "change-me"):
        raise HTTPException(401, "Staff access only")

@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")

@app.post("/api/consent")
def consent(body: ConsentIn):
    db.set_consent(body.session_id, body.consent)
    return db.get_profile(body.session_id)

@app.get("/api/profile/{sid}")
def profile(sid: str):
    return db.get_profile(sid)

@app.post("/api/chat")
def chat(body: ChatIn):
    msg = mask_pii(body.message.strip()[:1000])      # 1. privacy masking
    lang = g.detect_language(msg)                    # 2. language + intent
    intent = g.detect_intent(msg)
    prof = db.get_profile(body.session_id)
    if prof["consent"]:
        db.add_prefs(body.session_id, g.extract_prefs(msg))
        prof = db.get_profile(body.session_id)
    prefs = prof["prefs"]
    sources, mode, handoff = [], "rule", False

    if intent == "greeting":
        reply = ("Hello! I can help with hotel info (breakfast, Wi-Fi, check-out), local suggestions, "
                 "day plans, and service requests like towels, spa or a ride. What would you like to know?")
        mode = "rule"
    elif intent == "complaint":                      # 3. human hand-off
        rid = db.add_request(body.session_id, "complaint", msg)
        reply = f"I'm very sorry about this. I've alerted our duty manager (ticket #{rid}) and a team member will contact you shortly."
        handoff = True
    elif intent == "service_request":                # 4. mock service API
        kind = g.service_kind(msg)
        rid = db.add_request(body.session_id, kind, msg)
        reply = f"Done! I've sent your {kind.replace('_', ' ')} request to the team (ticket #{rid}). This is a demo/mock booking."
    elif intent == "plan":                           # 5. constraint-checked plan
        days, budget = g.parse_days(msg), g.parse_budget(msg)
        plan = g.build_plan(days, budget, prefs)
        if not any(plan):
            reply = "I couldn't build a plan within those limits. Could you raise the budget or tell me more?"
        else:
            reply = g.format_plan(plan)
        sources = [s["name"] for d in plan for s in d]
        mode = "constraint-checker"
    else:                                            # 6. grounded RAG answer
        items = rag.retrieve(msg)
        reply, mode = llm.answer(msg, items, prefs, lang)
        sources = [i["name"] for i in items]

    db.log_chat(body.session_id, intent, msg, reply)
    return {"reply": reply, "intent": intent, "language": lang, "sources": sources,
            "mode": mode, "handoff": handoff, "personalised": bool(prefs)}

@app.post("/api/feedback")
def feedback(body: FeedbackIn):
    db.add_feedback(body.session_id, max(1, min(5, body.rating)))
    return {"ok": True}

@app.get("/api/staff/requests")
def staff_requests(x_staff_token: str = Header(None)):
    staff_only(x_staff_token)
    return {"requests": db.list_requests(), "stats": db.stats()}

@app.post("/api/staff/requests/{rid}/{status}")
def staff_update(rid: int, status: str, x_staff_token: str = Header(None)):
    staff_only(x_staff_token)
    if status not in ("new", "in_progress", "done"):
        raise HTTPException(400, "bad status")
    db.set_request_status(rid, status)
    return {"ok": True}


# ---------- Requirements research: surveys + interviews ----------
class SurveyIn(BaseModel):
    role: str                      # "guest" or "staff"
    answers: dict

class InterviewIn(BaseModel):
    role: str
    participant_code: str          # e.g. "G01" - never use real names
    functional_needs: str = ""
    non_functional_needs: str = ""
    notes: str = ""

def _clean(v):
    """Mask personal data in anything typed by participants."""
    if isinstance(v, str): return mask_pii(v.strip()[:2000])
    if isinstance(v, list): return [_clean(x) for x in v][:30]
    return v

@app.get("/survey")
def survey_page():
    return FileResponse(STATIC / "survey.html")

@app.post("/api/survey")
def submit_survey(body: SurveyIn):
    if body.role not in ("guest", "staff"):
        raise HTTPException(400, "role must be guest or staff")
    answers = {k[:60]: _clean(v) for k, v in list(body.answers.items())[:40]}
    return {"ok": True, "id": db.add_survey(body.role, answers)}

@app.post("/api/staff/interview")
def submit_interview(body: InterviewIn, x_staff_token: str = Header(None)):
    staff_only(x_staff_token)
    if body.role not in ("guest", "staff"):
        raise HTTPException(400, "role must be guest or staff")
    rid = db.add_interview(body.role, _clean(body.participant_code)[:20], _clean(body.functional_needs),
                           _clean(body.non_functional_needs), _clean(body.notes))
    return {"ok": True, "id": rid}

@app.get("/api/staff/research")
def research_summary(x_staff_token: str = Header(None)):
    staff_only(x_staff_token)
    surveys, interviews = db.list_surveys(), db.list_interviews()
    # simple summary: how often each feature was chosen + average rating per quality
    feature_counts, rating_sums = {}, {}
    for r in surveys:
        for f in r["answers"].get("features", []) or []:
            feature_counts[f] = feature_counts.get(f, 0) + 1
        for k, v in r["answers"].items():
            if k.startswith("rate_") and str(v).isdigit():
                rating_sums.setdefault(k, []).append(int(v))
    avg = {k: round(sum(v) / len(v), 2) for k, v in rating_sums.items()}
    return {"survey_count": len(surveys), "interview_count": len(interviews),
            "feature_counts": feature_counts, "average_ratings": avg}

@app.get("/api/staff/export/{kind}")
def export_csv(kind: str, x_staff_token: str = Header(None)):
    staff_only(x_staff_token)
    out = io.StringIO(); w = csv.writer(out)
    if kind == "surveys":
        rows = db.list_surveys()
        keys = sorted({k for r in rows for k in r["answers"]})
        w.writerow(["id", "role"] + keys)
        for r in rows:
            w.writerow([r["id"], r["role"]] + [", ".join(v) if isinstance(v := r["answers"].get(k, ""), list) else v for k in keys])
    elif kind == "interviews":
        w.writerow(["id", "role", "participant_code", "functional_needs", "non_functional_needs", "notes"])
        for r in db.list_interviews():
            w.writerow([r["id"], r["role"], r["participant_code"], r["functional_needs"], r["non_functional_needs"], r["notes"]])
    else:
        raise HTTPException(404, "kind must be surveys or interviews")
    return PlainTextResponse(out.getvalue(), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename={kind}.csv"})
