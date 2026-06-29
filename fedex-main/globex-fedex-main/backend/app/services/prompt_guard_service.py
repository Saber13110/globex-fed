"""Détection heuristique d'injection de prompts (préférences et messages chat)."""

from __future__ import annotations

import base64
import re
import unicodedata
from dataclasses import dataclass
from enum import Enum

from app.core.config import get_settings
from app.services.llm.prompts import FEDEX_SYSTEM_PROMPT, SECURITY_RULES

# Seuil admin : au-delà, bouton Approuver désactivé (même en warn)
APPROVE_DISABLED_SCORE = 55


class RiskLevel(str, Enum):
    ok = "ok"
    warn = "warn"
    block = "block"


@dataclass
class RiskResult:
    score: int
    level: RiskLevel
    reasons: list[str]


_BLOCK_PATTERNS: list[tuple[str, re.Pattern[str], int]] = [
    ("ignore_instructions", re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", re.I), 75),
    (
        "ignore_instructions_fr",
        re.compile(
            r"(ignore[rz]?|oublie|oubliez)\s+(les\s+)?(instructions?|consignes?|r[eè]gles?)\s+(pr[eé]c[eé]dentes?|du\s+syst[eè]me)?",
            re.I,
        ),
        75,
    ),
    ("ignore_rules", re.compile(r"ignore\s+(tes|vos|the|all)\s+(r[eè]gles|rules|instructions?|prompts?)", re.I), 50),
    (
        "ignore_prompt_fr",
        re.compile(
            r"(ignore[rz]?|oublie[rz]?)\s+(tt\s+|tout\s+|tous\s+)?(les\s+)?(prompts?|consignes?|instructions?)",
            re.I,
        ),
        70,
    ),
    (
        "forget_prompt_fr",
        re.compile(
            r"(oublie[rz]?|forget|ignore[rz]?)\s+(le\s+|les\s+|ton\s+|tes\s+|all\s+)?(prompt|consignes?|instructions?)",
            re.I,
        ),
        75,
    ),
    (
        "forget_prompt_system_fr",
        re.compile(
            r"(oublie[rz]?|forget|ignore[rz]?).{0,30}(prompt|consignes?|instructions?).{0,45}"
            r"(syst[eè]me|systeme|pr[eé]c[eé]dent|donn[eé]|par\s+le\s+syst)",
            re.I,
        ),
        80,
    ),
    (
        "ignore_prompt_request",
        re.compile(
            r"veux\s+que\s+tu\s+ignor",
            re.I,
        ),
        45,
    ),
    (
        "system_prompt",
        re.compile(
            r"(reveal|show|print|display|donne|affiche|montre|r[eé]p[eè]te|copie|envoie).{0,50}"
            r"(system\s*prompt|prompt\s*(de\s+)?(ton|votre|le)\s*(syst[eè]me|systeme)|"
            r"prompt\s*syst[eè]me|tes\s+instructions?\s+syst[eè]me|instructions?\s+(du\s+)?syst[eè]me)",
            re.I,
        ),
        65,
    ),
    (
        "extract_system_prompt",
        re.compile(
            r"(prompt|instructions?)\s+(de\s+)?(ton|votre|le)\s+(syst[eè]me|systeme)",
            re.I,
        ),
        55,
    ),
    (
        "role_switch",
        re.compile(
            r"you\s+are\s+now|tu\s+es\s+maintenant|act\s+as\s+|jailbreak|DAN\s+mode|"
            r"mode\s+d[eé]veloppeur|developer\s+mode|sans\s+restrictions?|"
            r"(je\s+suis|i\s+am).{0,25}(d[eé]veloppeur|developer|devloppeur|ing[eé]nieur|administrateur|admin\b)",
            re.I,
        ),
        50,
    ),
    ("delimiter_injection", re.compile(r"<<<|>>>|===\s*SYSTEM|END_STYLE_HINTS|END_USER_MESSAGE", re.I), 40),
    ("role_tags", re.compile(r"^\s*(system|assistant|user)\s*:", re.I | re.M), 35),
    ("api_secrets", re.compile(r"(api[_\s-]?key|secret[_\s-]?key|password|mot\s+de\s+passe|bearer\s+)", re.I), 30),
    ("override", re.compile(r"override\s+(security|safety|rules)|contourne|bypass|contourner", re.I), 40),
    (
        "fake_fedex_status",
        re.compile(
            r"(invente|forge|fake|faux)\s+.{0,30}(statut|status|livraison|tracking)|"
            r"dis\s+que\s+.{0,20}(est\s+)?livr[eé]",
            re.I,
        ),
        45,
    ),
    (
        "extract_chatbot_code",
        re.compile(
            r"(code|source).{0,30}(chatbot|bot|application|backend|serveur|projet|api)|"
            r"(chatbot|bot|application|backend).{0,30}(code|source)",
            re.I,
        ),
        65,
    ),
    (
        "extract_secrets_request",
        re.compile(
            r"(donne|donne[rz]?|montre|affiche|envoie|partage|copie|r[eé]v[eè]le|give|show|share|send|leak).{0,40}"
            r"(cl[eé]\s*api|api\s*key|secret\s*key|prompt\s*syst|system\s*prompt|token|credentials?|"
            r"mot\s+de\s+passe|fichiers?\s+env|\.env|repo|github)",
            re.I,
        ),
        60,
    ),
    (
        "probe_secrets_fr",
        re.compile(
            r"(cl[eé]\s*api|api\s*key|secret\s*key|jwt|token\s*d'?acc[eè]s|identifiants?|"
            r"instructions?\s+secr[eè]tes?|architecture\s+interne|fonctionnement\s+interne|"
            r"comment\s+tu\s+(es|êtes)\s+(fait|construit|programm[eé]))",
            re.I,
        ),
        55,
    ),
    (
        "probe_internals",
        re.compile(
            r"(sous\s+le\s+capot|under\s+the\s+hood|stack\s+technique|mod[eè]le\s+utilis[eé]|"
            r"quelle\s+ia|quel\s+llm|base\s+de\s+donn[eé]es|fichier\s+\.env)",
            re.I,
        ),
        50,
    ),
    (
        "meta_system_injection",
        re.compile(
            r"tu\s+es\s+un\s+assistant\s+s[eé]curis[eé]|"
            r"messages?\s+utilisateur.{0,50}donn[eé]es?.{0,40}instructions?\s+syst[eè]me|"
            r"jamais\s+des\s+instructions\s+syst[eè]me|"
            r"tentative\s+de\s+prompt\s+injection|prompt\s+injection",
            re.I,
        ),
        75,
    ),
    (
        "bypass_security_fr",
        re.compile(
            r"contourn(er|e)\s+(les\s+)?r[eè]gles|bypass\s+(security|rules|safety)|"
            r"action\s+non\s+autoris[eé]e|modifier\s+(tes|vos|your)\s+instructions?|"
            r"r[eé]v[eè]l(er|e)\s+(tes|vos|your)\s+instructions?",
            re.I,
        ),
        70,
    ),
    (
        "change_role_fr",
        re.compile(
            r"chang(e|er)\s+(ton|votre|your)\s+r[oô]le|change\s+your\s+role|"
            r"nouveau\s+r[oô]le|new\s+role",
            re.I,
        ),
        55,
    ),
]

_WARN_PATTERNS: list[tuple[str, re.Pattern[str], int]] = [
    ("imperative", re.compile(r"\b(tu\s+dois|you\s+must|always\s+pretend|fais\s+comme\s+si)\b", re.I), 15),
    ("long_instruction", re.compile(r"(instruction|consigne|règle)\s*:", re.I), 12),
    ("pretend_role", re.compile(r"pr[eé]tend(s|re)?\s+être", re.I), 12),
    (
        "sensitive_question",
        re.compile(
            r"(peux|pourrais|tu\s+peux).{0,30}(donne|montre|affiche|envoie).{0,40}(code|secret|prompt|cl[eé])",
            re.I,
        ),
        35,
    ),
]

_BASE64_LIKE = re.compile(r"[A-Za-z0-9+/]{48,}={0,2}")


def _looks_like_base64_payload(text: str) -> bool:
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


def sanitize_style_hints(text: str, *, max_len: int = 800) -> str:
    cleaned = (text or "").strip()[:max_len]
    cleaned = re.sub(r"<<<|>>>", "", cleaned)
    return cleaned


def _normalize_for_scan(text: str) -> str:
    """Normalise accents et espaces pour la détection (FR/EN)."""
    raw = (text or "").strip()
    folded = unicodedata.normalize("NFKD", raw)
    without_accents = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", without_accents)


def assess_text(text: str) -> RiskResult:
    settings = get_settings()
    if not settings.prompt_guard_enabled:
        return RiskResult(score=0, level=RiskLevel.ok, reasons=[])

    raw = _normalize_for_scan(text)
    if not raw:
        return RiskResult(score=0, level=RiskLevel.ok, reasons=[])

    from app.services.gpt.memory_service import detect_language_preference

    if detect_language_preference(text):
        return RiskResult(score=0, level=RiskLevel.ok, reasons=[])

    from app.services.llm.tracking_extract import extract_tracking_number

    if extract_tracking_number(text) and re.search(
        r"\b(suiv|track|colis|numero|num[eé]ro|exp[eé]dition)\b",
        raw,
        re.I,
    ):
        return RiskResult(score=0, level=RiskLevel.ok, reasons=[])

    score = 0
    reasons: list[str] = []
    for code, pattern, weight in _BLOCK_PATTERNS:
        if pattern.search(raw):
            score += weight
            reasons.append(code)
    for code, pattern, weight in _WARN_PATTERNS:
        if pattern.search(raw):
            score += weight
            if code not in reasons:
                reasons.append(code)

    if _looks_like_base64_payload(raw):
        score += 50
        reasons.append("base64_obfuscation")

    score = min(score, 100)
    force_block_reasons = {
        "extract_chatbot_code",
        "extract_secrets_request",
        "system_prompt",
        "extract_system_prompt",
        "ignore_instructions",
        "ignore_instructions_fr",
        "ignore_prompt_fr",
        "forget_prompt_fr",
        "forget_prompt_system_fr",
        "probe_secrets_fr",
        "meta_system_injection",
        "bypass_security_fr",
        "change_role_fr",
    }
    if score >= 55 and any(r in force_block_reasons for r in reasons):
        level = RiskLevel.block
    elif score >= settings.prompt_guard_block_threshold:
        level = RiskLevel.block
    elif score >= settings.prompt_guard_warn_threshold:
        level = RiskLevel.warn
    else:
        level = RiskLevel.ok

    return RiskResult(score=score, level=level, reasons=reasons)


def assess_preference_text(text: str) -> RiskResult:
    return assess_text(text)


_STRICT_ATTACK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"(ignore[rz]?|oublie[rz]?)\s+.{0,20}(instructions?|consignes?|r[eè]gles?|prompts?)",
        re.I,
    ),
    re.compile(
        r"(reveal|show|print|display|donne|affiche|montre|r[eé]v[eè]le|copie|envoie).{0,40}"
        r"(system\s*prompt|prompt\s*syst[eè]me|cl[eé]s?\s*api|api\s*key|secret)",
        re.I,
    ),
    re.compile(r"\b(jailbreak|DAN\s+mode|contourne|bypass|contourner)\b", re.I),
    re.compile(
        r"(supprime|delete|efface).{0,30}(sans\s+permission|without\s+permission)",
        re.I,
    ),
]

_LEGITIMATE_COPILOT_RE = re.compile(
    r"\b("
    r"pdf|excel|xlsx|export|g[eé]n[eè]r|notif|tracking|logs?|utilisateurs?|users?|"
    r"tickets?|conversations?|derni[eè]res?|affiche|liste|donne|comptes?|"
    r"plateforme|platform|dashboard|kpi|activit[eé]|r[eé]sum[eé]|retards?|incidents?|"
    r"rapport|report|export|preview|partager|partage"
    r")\b",
    re.I,
)


def is_strict_security_attack(text: str) -> bool:
    raw = _normalize_for_scan(text)
    if not raw:
        return False
    return any(p.search(raw) for p in _STRICT_ATTACK_PATTERNS)


def is_legitimate_copilot_request(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    if is_strict_security_attack(raw):
        return False
    return bool(_LEGITIMATE_COPILOT_RE.search(raw)) or bool(
        re.search(r"^(bonjour|bonsoir|salut|hello)\b", raw, re.I)
    )


def assess_user_message(text: str, *, ui_language: str | None = None) -> RiskResult:
    from app.services.client_phase12.capabilities import smart_guard_enabled

    if smart_guard_enabled():
        from app.services.client_phase12.threat_assessment import assess_message_threat

        return assess_message_threat(text, ui_language=ui_language)

    if is_strict_security_attack(text):
        result = assess_text(text)
        if result.level != RiskLevel.block:
            return RiskResult(
                score=max(result.score, 80),
                level=RiskLevel.block,
                reasons=[*result.reasons, "strict_security_attack"],
            )
        return result
    if is_legitimate_copilot_request(text):
        return RiskResult(score=0, level=RiskLevel.ok, reasons=["legitimate_copilot"])
    try:
        from app.services.admin_client.dashboard.dashboard_workspace import is_dashboard_workspace

        if is_dashboard_workspace(text):
            return RiskResult(score=0, level=RiskLevel.ok, reasons=["admin_dashboard"])
    except ImportError:
        pass
    try:
        from app.services.admin_client.reports.reports_workspace import is_reports_workspace

        if is_reports_workspace(text):
            return RiskResult(score=0, level=RiskLevel.ok, reasons=["admin_reports"])
    except ImportError:
        pass
    result = assess_text(text)
    if result.level == RiskLevel.block:
        return result
    return result


def must_block_preferences(result: RiskResult) -> bool:
    settings = get_settings()
    if not settings.prompt_guard_enabled:
        return False
    return result.level == RiskLevel.block


def must_block_approve(result: RiskResult) -> bool:
    """Bloque l'approbation admin si block ou score trop élevé."""
    if must_block_preferences(result):
        return True
    return result.score >= APPROVE_DISABLED_SCORE


def approve_disabled_for_submission(risk_score: int, risk_reasons: list[str] | None = None) -> bool:
    """Utilisé par l'UI admin pour désactiver le bouton Approuver."""
    if risk_score >= get_settings().prompt_guard_block_threshold:
        return True
    if risk_score >= APPROVE_DISABLED_SCORE:
        return True
    if risk_reasons and "base64_obfuscation" in risk_reasons:
        return True
    return False


_PII_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PII_PHONE = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{2,4}[-.\s]?\d{2,4}[-.\s]?\d{0,4}\b")


def filter_model_output(text: str) -> tuple[str, bool]:
    """Masque fuites évidentes du prompt système, secrets et PII courantes."""
    if not text:
        return text, False
    redacted = False
    out = text
    for snippet in (SECURITY_RULES[:120], FEDEX_SYSTEM_PROMPT[:80], "GEMINI_API_KEY", "JWT_SECRET"):
        if snippet and snippet in out:
            out = out.replace(snippet, "[…]")
            redacted = True
    if re.search(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+\.", out):
        out = re.sub(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[token]", out)
        redacted = True
    if _PII_EMAIL.search(out):
        out = _PII_EMAIL.sub("[email masqué]", out)
        redacted = True
    return out, redacted
