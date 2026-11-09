import re
from .rag import KB

def detect_language(text):
    if re.search(r"[\u0D80-\u0DFF]", text): return "si"
    if re.search(r"[\u0B80-\u0BFF]", text): return "ta"
    return "en"

def detect_intent(text):
    t = text.lower().strip()
    if re.fullmatch(r"(hi+|hello+|hey+|good (morning|afternoon|evening)|thanks?( you)?|thank you|bye|ok(ay)?|ayubowan|vanakkam)[\s!.]*", t):
        return "greeting"
    if re.search(r"complain|terrible|awful|dirty|broken|not working|unacceptable|refund|manager", t): return "complaint"
    if re.search(r"\b(book|order|send|arrange|need|request|clean|towels?)\b", t) and \
       re.search(r"housekeeping|towels?|clean|room service|food|spa|massage|ride|taxi|cab|transfer", t): return "service_request"
    if re.search(r"plan|itinerary|schedule|day trip|\d+[- ]?day", t): return "plan"
    if re.search(r"recommend|suggest|where should|best|any good|ideas", t): return "recommend"
    return "info"

def extract_prefs(text):
    """Only called when the guest has given consent."""
    t = text.lower()
    prefs = []
    for word in ["vegetarian", "vegan", "seafood", "history", "culture", "beach", "budget", "shopping", "spa", "family"]:
        if word in t: prefs.append(word)
    return prefs

SERVICE_KINDS = {"housekeeping": ["housekeeping", "towel", "clean"], "food_order": ["room service", "food", "order"],
                 "spa": ["spa", "massage"], "ride": ["ride", "taxi", "cab", "transfer"]}

def service_kind(text):
    t = text.lower()
    for kind, words in SERVICE_KINDS.items():
        if any(w in t for w in words): return kind
    return "other"

def parse_budget(text):
    m = re.search(r"(?:usd|\$)\s?(\d+)|(\d+)\s?(?:usd|dollars)", text.lower())
    if m: return int(m.group(1) or m.group(2))
    return None

def parse_days(text):
    m = re.search(r"(\d+)[- ]?day", text.lower())
    return max(1, min(int(m.group(1)), 5)) if m else 1

def _open_during(item, start_h, end_h):
    a, b = item["open"].split("-")
    oa, ob = int(a[:2]), int(b[:2])
    return oa <= start_h and ob >= end_h

SLOTS = [("Morning", 9, 12, "activity"), ("Lunch", 12, 14, "dining"),
         ("Afternoon", 14, 17, "activity"), ("Evening", 18, 21, "dining")]

def build_plan(days, budget_per_day, prefs):
    """Constraint checker: only shows items that fit budget, opening hours, and are not repeated."""
    used, plan = set(), []
    for d in range(1, days + 1):
        remaining = budget_per_day if budget_per_day is not None else 10**6
        day = []
        for label, s, e, cat in SLOTS:
            options = [i for i in KB if i["category"] == cat and i["id"] not in used
                       and i["price"] <= remaining and _open_during(i, s, e)
                       and not (("vegetarian" in prefs or "vegan" in prefs) and "not vegetarian" in i["text"].lower())
                       and "day trip" not in i["name"].lower()]
            if not options: continue
            # rank: preference matches first, then cheaper
            options.sort(key=lambda i: (-sum(p in (i["text"] + i["name"]).lower() for p in prefs), i["price"]))
            pick = options[0]
            used.add(pick["id"]); remaining -= pick["price"]
            day.append({"slot": label, "name": pick["name"], "price": pick["price"], "id": pick["id"]})
        plan.append(day)
    return plan

def format_plan(plan):
    lines, total = [], 0
    for i, day in enumerate(plan, 1):
        lines.append(f"Day {i}:")
        for s in day:
            lines.append(f"  - {s['slot']}: {s['name']} (USD {s['price']})")
            total += s["price"]
    lines.append(f"Estimated total per person: USD {total}. All items checked against budget and opening hours.")
    return "\n".join(lines)
