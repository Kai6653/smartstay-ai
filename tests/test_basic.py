import os, pytest
os.environ["LLM_PROVIDER"] = "none"
from fastapi.testclient import TestClient
from app import db
db.DB_PATH = "test_smartstay.db"
from app.main import app
from app.privacy import mask_pii
from app import guardrails as g

client = TestClient(app)

def chat(msg, sid="t1"):
    return client.post("/api/chat", json={"session_id": sid, "message": msg}).json()

def test_privacy_masking():
    out = mask_pii("email me at a.b@x.com or call +94 77 123 4567")
    assert "a.b@x.com" not in out and "[EMAIL]" in out and "[PHONE]" in out

def test_grounded_answer():
    r = chat("What time is breakfast?")
    assert "06:30" in r["reply"] and r["sources"]

def test_unknown_question_does_not_hallucinate():
    r = chat("Do you have a helicopter pad?")
    assert "don't have" in r["reply"].lower()

def test_service_request_and_staff_dashboard():
    r = chat("Please send extra towels to my room")
    assert r["intent"] == "service_request" and "ticket" in r["reply"]
    s = client.get("/api/staff/requests", headers={"X-Staff-Token": "change-me"})
    assert s.status_code == 200 and len(s.json()["requests"]) >= 1
    assert client.get("/api/staff/requests").status_code == 401

def test_complaint_handoff():
    assert chat("The room is dirty, I want the manager")["handoff"] is True

def test_plan_respects_budget():
    plan = g.build_plan(1, 30, [])
    assert sum(s["price"] for s in plan[0]) <= 30

def test_consent_required_for_prefs():
    chat("I am vegetarian", sid="nc")
    assert db.get_profile("nc")["prefs"] == []
    client.post("/api/consent", json={"session_id": "nc", "consent": True})
    chat("I am vegetarian", sid="nc")
    assert "vegetarian" in db.get_profile("nc")["prefs"]
    client.post("/api/consent", json={"session_id": "nc", "consent": False})
    assert db.get_profile("nc")["prefs"] == []

def teardown_module(m):
    if os.path.exists("test_smartstay.db"): os.remove("test_smartstay.db")

def test_survey_and_interview_flow():
    r = client.post("/api/survey", json={"role": "guest", "answers": {
        "features": ["Answer hotel questions"], "rate_privacy": "5", "comments": "call me on +94 77 123 4567"}})
    assert r.status_code == 200
    assert client.post("/api/survey", json={"role": "hacker", "answers": {}}).status_code == 400
    H = {"X-Staff-Token": "change-me"}
    i = client.post("/api/staff/interview", headers=H, json={"role": "staff", "participant_code": "S01",
                    "functional_needs": "fast room requests", "non_functional_needs": "privacy"})
    assert i.status_code == 200
    assert client.post("/api/staff/interview", json={"role": "staff", "participant_code": "S02"}).status_code == 401
    summary = client.get("/api/staff/research", headers=H).json()
    assert summary["survey_count"] >= 1 and summary["average_ratings"]["rate_privacy"] == 5.0
    csv_text = client.get("/api/staff/export/surveys", headers=H).text
    assert "+94 77" not in csv_text and "[PHONE]" in csv_text
    assert "S01" in client.get("/api/staff/export/interviews", headers=H).text
