# SmartStay AI
A Generative-AI, prompt-based assistant for personalised hospitality and tourism services (MIS 4500 capstone).

## Features
- Chat for pre-arrival, in-stay and local-tourism questions
- Answers grounded in a verified knowledge base (simple RAG) with sources shown
- Intent + language detection
- Consent-based guest profile (preferences saved only if the guest ticks the box; unticking deletes them)
- PII masking (email, phone, card, passport) before logging or sending to the AI model
- Constraint checker: day plans respect budget and opening hours
- Mock service APIs (housekeeping, food, spa, ride) and complaint hand-off to humans
- Staff dashboard (token protected), calm fallback if the AI model fails

## Run
```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # optional: add ANTHROPIC_API_KEY
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000. Staff tab token: `change-me` (set `STAFF_TOKEN` to change).
Without an API key the bot still works, replying only from verified facts.

## Test
```bash
pytest -q
```

## Structure
```
app/main.py        API + orchestration      app/guardrails.py  intent, plans, constraints
app/rag.py         retrieval                app/llm.py         prompt + model + fallback
app/privacy.py     PII masking              app/db.py          SQLite
app/knowledge.json sample hotel data        static/index.html  chat + staff UI
```
