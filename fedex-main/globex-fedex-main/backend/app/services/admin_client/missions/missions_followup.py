"""Suite de dialogue Mission Control — relances après liste."""

from __future__ import annotations

import re

_MISSIONS_HISTORY_MARKERS = re.compile(
    r"Missions\s+agent|Agent\s+missions|"
    r"\|\s*#\s*\d{1,8}\s*\|.{0,40}mission|"
    r"mission\s*#\s*\d{1,8}",
    re.I,
)

_MISSION_HASH_RE = re.compile(r"\bmission\s*#\s*(\d{1,8})\b", re.I)
_MISSION_BARE_RE = re.compile(r"\bmission\s+(\d{1,8})\b", re.I)
_LIST_ROW_RE = re.compile(r"^\s*-\s*#\s*(\d{1,8})\s*\|", re.MULTILINE)

_FOLLOWUP_ACTION_RE = re.compile(
    r"\b("
    r"r[eé]sultats?|logs?|journal|r[eé]sum[eé]|synth[eè]se|"
    r"relancer|r[eé]essayer|retry|reprendre|resume|"
    r"annuler|cancel|supprimer|delete|d[eé]tail"
    r")\b",
    re.I,
)


def is_missions_history_context(history_text: str) -> bool:
    return bool(_MISSIONS_HISTORY_MARKERS.search(history_text or ""))


def is_missions_followup_message(message: str, *, history_text: str = "") -> bool:
    text = (message or "").strip()
    if not text or not is_missions_history_context(history_text):
        return False
    if extract_mission_ref(text, history_text=history_text) is not None:
        return True
    return bool(_FOLLOWUP_ACTION_RE.search(text))


def extract_mission_ref(message: str, *, history_text: str = "") -> int | None:
    text = (message or "").strip()
    if not text:
        return None
    m = _MISSION_HASH_RE.search(text)
    if m:
        return int(m.group(1))
    m = _MISSION_BARE_RE.search(text)
    if m:
        return int(m.group(1))
    if is_missions_history_context(history_text):
        m = re.search(r"\b(?:la|le)\s+mission\s+(\d{1,8})\b", text, re.I)
        if m:
            return int(m.group(1))
        m = re.search(r"^\s*#?\s*(\d{1,8})\s*$", text)
        if m:
            num = int(m.group(1))
            ids = list_mission_ids_from_history(history_text)
            if num in ids:
                return num
            if ids and 1 <= num <= len(ids) and num <= 25:
                return ids[num - 1]
            return num
    return None


def list_mission_ids_from_history(history_text: str) -> list[int]:
    ids: list[int] = []
    for pattern in (_LIST_ROW_RE, re.compile(r"#\s*(\d{1,8})\s*\|", re.MULTILINE)):
        for m in pattern.finditer(history_text or ""):
            mid = int(m.group(1))
            if mid not in ids:
                ids.append(mid)
    return ids


def wants_last_failed_mission(message: str) -> bool:
    return bool(
        re.search(
            r"\b(derni[eè]re|last)\s+mission\s+([eé]chou[eé]e|failed)\b",
            message or "",
            re.I,
        )
    )
