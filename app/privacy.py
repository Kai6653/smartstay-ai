import re

PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[EMAIL]"),
    (re.compile(r"\b(?:\d[ -]?){13,16}\b"), "[CARD]"),
    (re.compile(r"\+?\d[\d ()-]{8,}\d"), "[PHONE]"),
    (re.compile(r"\b[A-Z]{1,2}\d{6,8}\b"), "[PASSPORT]"),
]

def mask_pii(text: str) -> str:
    """Hide personal data before it is logged or sent to the AI model."""
    for pat, tag in PATTERNS:
        text = pat.sub(tag, text)
    return text
