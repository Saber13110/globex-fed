import re

# FedEx : souvent 12 ou 14 chiffres, ou formats alphanumériques (MVP : heuristique simple).
_TRACKING_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(\d{12})\b"),
    re.compile(r"\b(\d{14})\b"),
    re.compile(r"\b(\d{10,22})\b"),
    re.compile(r"\b([A-Z]{2}\d{9}[A-Z]{2})\b", re.IGNORECASE),
]

_ALPHANUM_CANDIDATE = re.compile(r"\b([A-Z0-9]{10,22})\b", re.IGNORECASE)
_MIN_TRACKING_DIGITS = 8


def is_plausible_tracking_number(value: str) -> bool:
    """Filtre les faux positifs (mots français, etc.) — un vrai suivi contient assez de chiffres."""
    candidate = (value or "").strip().upper()
    if len(candidate) < 10 or len(candidate) > 22:
        return False
    digits = sum(ch.isdigit() for ch in candidate)
    if digits >= _MIN_TRACKING_DIGITS:
        return True
    if _TRACKING_PATTERNS[3].fullmatch(candidate):
        return True
    return False


def extract_tracking_numbers(text: str) -> list[str]:
    found: list[str] = []
    for pattern in _TRACKING_PATTERNS:
        for match in pattern.finditer(text):
            tn = match.group(1).upper() if match.lastindex else match.group(0).upper()
            if is_plausible_tracking_number(tn) and tn not in found:
                found.append(tn)

    for match in _ALPHANUM_CANDIDATE.finditer(text):
        tn = match.group(1).upper()
        if is_plausible_tracking_number(tn) and tn not in found:
            found.append(tn)
    return found


def first_tracking_number(text: str) -> str | None:
    numbers = extract_tracking_numbers(text)
    return numbers[0] if numbers else None
