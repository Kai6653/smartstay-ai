import os
import httpx

SYSTEM = """You are SmartStay AI, a hotel and local-tourism assistant for one sample hotel in Colombo.
RULES:
1. Answer ONLY using the FACTS provided. If the facts do not contain the answer, say you don't have that
   information and offer to connect the guest with hotel staff. Never invent prices, hours or policies.
2. Reply in the guest's language. Be warm, concise (max 5 sentences).
3. Personalise using guest preferences when they are given.
4. Never ask for passwords, card numbers or passport numbers."""

def fallback_answer(items, prefs):
    """Used when Ollama is unavailable: replies from verified facts only."""
    if not items:
        return ("I'm sorry, I don't have verified information about that. "
                "Would you like me to connect you with our front desk team?")
    lines = ["Here is what I found:"]
    for i in items:
        price = "free" if i["price"] == 0 else f"USD {i['price']}"
        lines.append(f"- {i['name']}: {i['text']} (Price: {price}, hours {i['open']})")
    if prefs:
        lines.append(f"(Personalised using your saved preferences: {', '.join(prefs)}.)")
    return "\n".join(lines)

def answer(question_masked, items, prefs, language):
    if os.getenv("LLM_PROVIDER", "ollama") == "none" or not items:
        return fallback_answer(items, prefs), "offline"

    host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "llama3.2")
    key = os.getenv("OLLAMA_API_KEY", "")          # only needed for Ollama cloud (https://ollama.com)
    headers = {"Authorization": f"Bearer {key}"} if key else {}

    facts = "\n".join(f"- {i['name']} | USD {i['price']} | hours {i['open']} | {i['text']}" for i in items)
    user = (f"FACTS:\n{facts}\n\nGUEST PREFERENCES: {', '.join(prefs) or 'none'}\n"
            f"GUEST LANGUAGE: {language}\n\nQUESTION: {question_masked}")
    try:
        r = httpx.post(f"{host}/api/chat", headers=headers, timeout=60, json={
            "model": model, "stream": False,
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]})
        r.raise_for_status()
        return r.json()["message"]["content"], "llm"
    except Exception:
        # Reliability requirement: calm fallback if the model/service fails
        return fallback_answer(items, prefs), "fallback"
