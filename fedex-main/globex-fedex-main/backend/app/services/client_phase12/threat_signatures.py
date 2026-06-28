"""Signatures d'attaque haute confiance — FR + EN."""

from __future__ import annotations

import base64
import re
import unicodedata

FORCE_BLOCK_CODES = frozenset(
    {
        "ignore_instructions",
        "ignore_instructions_fr",
        "ignore_prompt_fr",
        "forget_prompt_fr",
        "forget_prompt_system_fr",
        "system_prompt",
        "extract_system_prompt",
        "extract_secrets_request",
        "probe_secrets_fr",
        "meta_system_injection",
        "bypass_security_fr",
        "jailbreak",
        "delimiter_injection",
        "role_tags",
        "base64_obfuscation",
    }
)

_HIGH_PATTERNS: list[tuple[str, re.Pattern[str], int]] = [
    ("ignore_instructions", re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", re.I), 85),
    (
        "ignore_instructions_fr",
        re.compile(
            r"(ignore[rz]?|oublie|oubliez)\s+(les\s+)?(instructions?|consignes?|r[eè]gles?)\s+"
            r"(pr[eé]c[eé]dentes?|du\s+syst[eè]me)?",
            re.I,
        ),
        85,
    ),
    (
        "ignore_prompt_fr",
        re.compile(
            r"(ignore[rz]?|oublie[rz]?)\s+(tt\s+|tout\s+|tous\s+)?(les\s+)?(prompts?|consignes?|instructions?)",
            re.I,
        ),
        80,
    ),
    (
        "forget_prompt_fr",
        re.compile(
            r"(oublie[rz]?|forget|ignore[rz]?)\s+(le\s+|les\s+|ton\s+|tes\s+|all\s+)?"
            r"(prompt|consignes?|instructions?)",
            re.I,
        ),
        80,
    ),
    (
        "forget_prompt_system_fr",
        re.compile(
            r"(oublie[rz]?|forget|ignore[rz]?).{0,30}(prompt|consignes?|instructions?).{0,45}"
            r"(syst[eè]me|systeme|pr[eé]c[eé]dent|donn[eé]|par\s+le\s+syst)",
            re.I,
        ),
        85,
    ),
    (
        "system_prompt",
        re.compile(
            r"(reveal|show|print|display|donne|affiche|montre|r[eé]p[eè]te|copie|envoie).{0,50}"
            r"(system\s*prompt|prompt\s*(de\s+)?(ton|votre|le)\s*(syst[eè]me|systeme)|"
            r"prompt\s*syst[eè]me|tes\s+instructions?\s+syst[eè]me|instructions?\s+(du\s+)?syst[eè]me)",
            re.I,
        ),
        80,
    ),
    (
        "extract_system_prompt",
        re.compile(
            r"(prompt|instructions?)\s+(de\s+)?(ton|votre|le)\s+(syst[eè]me|systeme)",
            re.I,
        ),
        75,
    ),
    (
        "extract_secrets_request",
        re.compile(
            r"(donne|donne[rz]?|montre|affiche|envoie|partage|copie|r[eé]v[eè]le|give|show|share|send|leak).{0,40}"
            r"(cl[eé]\s*api|api\s*key|secret|prompt\s*syst|system\s*prompt|token|credentials?|"
            r"mot\s+de\s+passe|\.env|fichier\s+env)",
            re.I,
        ),
        85,
    ),
    (
        "probe_secrets_fr",
        re.compile(
            r"(cl[eé]\s*api|api\s*key|secret\s*key|jwt|token\s*d'?acc[eè]s|"
            r"instructions?\s+secr[eè]tes?|fichier\s+\.env)",
            re.I,
        ),
        75,
    ),
    (
        "jailbreak",
        re.compile(
            r"\b(jailbreak|DAN\s+mode|mode\s+d[eé]veloppeur|developer\s+mode|"
            r"sans\s+restrictions?|tu\s+es\s+maintenant\s+admin|you\s+are\s+now\s+admin)\b",
            re.I,
        ),
        80,
    ),
    (
        "bypass_security_fr",
        re.compile(
            r"contourn(er|e)\s+(les\s+)?r[eè]gles|bypass\s+(security|rules|safety)|"
            r"r[eé]v[eè]l(er|e)\s+(tes|vos|your)\s+instructions?",
            re.I,
        ),
        80,
    ),
    (
        "meta_system_injection",
        re.compile(
            r"tentative\s+de\s+prompt\s+injection|prompt\s+injection|"
            r"messages?\s+utilisateur.{0,50}instructions?\s+syst[eè]me",
            re.I,
        ),
        85,
    ),
    ("delimiter_injection", re.compile(r"<<<|>>>|===\s*SYSTEM|END_STYLE_HINTS|END_USER_MESSAGE", re.I), 75),
    ("role_tags", re.compile(r"^\s*(system|assistant|user)\s*:", re.I | re.M), 70),
]

_MEDIUM_PATTERNS: list[tuple[str, re.Pattern[str], int]] = [
    ("override", re.compile(r"override\s+(security|safety|rules)|contourne|bypass|contourner", re.I), 45),
    (
        "extract_chatbot_code",
        re.compile(
            r"(donne|montre|affiche|envoie|give|show).{0,30}(code|source).{0,30}"
            r"(chatbot|backend|serveur|application|api)",
            re.I,
        ),
        55,
    ),
    (
        "probe_internals",
        re.compile(
            r"(sous\s+le\s+capot|under\s+the\s+hood|stack\s+technique|quelle\s+ia|quel\s+llm)",
            re.I,
        ),
        40,
    ),
    (
        "change_role_fr",
        re.compile(
            r"chang(e|er)\s+(ton|votre|your)\s+r[oô]le|change\s+your\s+role|nouveau\s+r[oô]le",
            re.I,
        ),
        45,
    ),
]

_WARN_PATTERNS: list[tuple[str, re.Pattern[str], int]] = [
    ("imperative", re.compile(r"\b(tu\s+dois|you\s+must|always\s+pretend|fais\s+comme\s+si)\b", re.I), 15),
    ("long_instruction", re.compile(r"(instruction|consigne|r[eè]gle)\s*:", re.I), 12),
]

_BASE64_LIKE = re.compile(r"[A-Za-z0-9+/]{48,}={0,2}")


def normalize_for_scan(text: str) -> str:
    raw = (text or "").strip()
    folded = unicodedata.normalize("NFKD", raw)
    without_accents = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", without_accents)


def looks_like_base64_jailbreak(text: str) -> bool:
    for match in _BASE64_LIKE.findall(text):
        if len(match) < 48:
            continue
        try:
            decoded = base64.b64decode(match + "==", validate=False)
            if len(decoded) >= 16 and decoded.isascii():
                sample = decoded.decode("ascii", errors="ignore").lower()
                if any(k in sample for k in ("ignore", "system", "instruction", "prompt", "jailbreak")):
                    return True
        except (ValueError, UnicodeDecodeError):
            continue
    return False


def scan_threat_signatures(text: str) -> tuple[int, list[str], bool]:
    """Retourne (score_max, reasons, force_block)."""
    raw = normalize_for_scan(text)
    if not raw:
        return 0, [], False

    reasons: list[str] = []
    max_score = 0
    force_block = False

    for code, pattern, weight in _HIGH_PATTERNS:
        if pattern.search(raw):
            reasons.append(code)
            max_score = max(max_score, weight)
            if code in FORCE_BLOCK_CODES:
                force_block = True

    medium_hits = 0
    medium_max = 0
    for code, pattern, weight in _MEDIUM_PATTERNS:
        if pattern.search(raw):
            reasons.append(code)
            medium_max = max(medium_max, weight)
            medium_hits += 1
    if medium_hits >= 2:
        max_score = max(max_score, medium_max + 15)
    elif medium_hits == 1:
        max_score = max(max_score, medium_max)

    warn_max = 0
    for code, pattern, weight in _WARN_PATTERNS:
        if pattern.search(raw):
            if code not in reasons:
                reasons.append(code)
            warn_max = max(warn_max, weight)
    max_score = max(max_score, warn_max)

    if looks_like_base64_jailbreak(raw):
        reasons.append("base64_obfuscation")
        max_score = max(max_score, 85)
        force_block = True

    return min(max_score, 100), reasons, force_block
