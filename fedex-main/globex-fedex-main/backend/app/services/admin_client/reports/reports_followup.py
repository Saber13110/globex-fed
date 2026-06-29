"""Suite de dialogue Centre de rapports — relances après liste/preview."""

from __future__ import annotations

import re

_REPORTS_HISTORY_MARKERS = re.compile(
    r"Centre de rapports Admin|Admin Reports Center|"
    r"Exports récents|Recent exports|"
    r"Catalogue des rapports|Report catalog|"
    r"Exports générés|Generated exports|"
    r"\#\d{1,8}\s+.+\((xlsx|csv|json|pdf)\)",
    re.I,
)

_FOLLOWUP_ACTION_RE = re.compile(
    r"\b("
    r"previsualis\w*|pr[eé]v\w+|prev\w+|preview|aper[cç]u|"
    r"t[eé]l[eé]charg\w*|telecharg\w*|download|redownload|"
    r"partage|share|envo(?:ie|ye)|consulte|d[eé]tails?"
    r")\b",
    re.I,
)

_RUN_HASH_RE = re.compile(r"#\s*(\d{1,8})\b")
_RUN_REF_RE = re.compile(
    r"\b(?:rapport|report|run|export)\s*#?\s*(\d{1,8})\b",
    re.I,
)
_RUN_LE_RE = re.compile(
    r"\b(?:le|la|num[eé]ro|n°)\s*#?\s*(\d{1,8})\b",
    re.I,
)


def is_reports_history_context(history_text: str) -> bool:
    return bool(_REPORTS_HISTORY_MARKERS.search(history_text or ""))


def is_reports_followup_message(message: str, *, history_text: str = "") -> bool:
    """Relance reports après une réponse Centre de rapports (preview, #N, téléchargement…)."""
    from app.services.admin_client.email.email_patterns import is_send_user_email_message

    text = (message or "").strip()
    if not text or not is_reports_history_context(history_text):
        return False
    if is_send_user_email_message(text):
        return False
    return bool(_FOLLOWUP_ACTION_RE.search(text))


def extract_report_run_ref(message: str, *, history_text: str = "") -> int | None:
    """#N, rapport N, le N — dans un fil reports."""
    text = (message or "").strip()
    if not text:
        return None

    m = _RUN_HASH_RE.search(text)
    if m:
        return int(m.group(1))

    m = _RUN_REF_RE.search(text)
    if m:
        return int(m.group(1))

    if is_reports_history_context(history_text):
        m = _RUN_LE_RE.search(text)
        if m:
            return int(m.group(1))

    return None
