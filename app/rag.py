import json, re
from pathlib import Path

KB = json.loads((Path(__file__).parent / "knowledge.json").read_text(encoding="utf-8"))
STOP = set("the a an is are to of in for and or at on do you i we what can how with my me it be".split())

def tokens(s):
    return [w for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in STOP]

def retrieve(query, k=3, min_score=1):
    """Simple keyword retrieval over the trusted knowledge set (swap for FAISS/Chroma later)."""
    q = set(tokens(query))
    scored = []
    for item in KB:
        words = set(tokens(item["name"] + " " + item["text"] + " " + item["category"]))
        score = len(q & words)
        if score >= min_score:
            scored.append((score, item))
    scored.sort(key=lambda x: -x[0])
    return [i for _, i in scored[:k]]
