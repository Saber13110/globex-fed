"""
Logique métier suspendu vs suspendable — sans modifier les outils existants.

Un compte est « suspendu » uniquement si un indicateur explicite le confirme.
Les alertes sécurité avec recommended_action=suspend_user → « suspendable / à surveiller ».
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.ai_assistant.safe_tool_executor import execute_tool_plan

_FAST_DEADLINE = 3.0

_SUSPENDABLE_THREATS = frozenset({
    "prompt_injection", "injection", "abuse", "bruteforce", "brute_force",
    "failed_login", "login_failure", "credential_stuffing",
})

_SUSPENDABLE_ACTIONS = frozenset({"suspend_user", "suspend"})


def is_truly_suspended(user: dict[str, Any]) -> bool:
    """Vrai uniquement si le compte est réellement suspendu sur la plateforme."""
    if not isinstance(user, dict):
        return False
    status = str(
        user.get("status") or user.get("statut") or user.get("account_status") or ""
    ).lower().strip()
    if status == "suspended":
        return True
    if user.get("is_suspended") is True:
        return True
    if user.get("disabled") is True:
        return True
    if user.get("suspended_at"):
        return True
    return False


def filter_suspended_users(users: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [u for u in users if isinstance(u, dict) and is_truly_suspended(u)]


def _incident_marks_suspendable(inc: dict[str, Any]) -> bool:
    if not isinstance(inc, dict):
        return False
    action = str(inc.get("recommended_action") or "").lower().strip()
    if action in _SUSPENDABLE_ACTIONS:
        return True
    score = inc.get("score") or inc.get("risk_score") or 0
    try:
        if float(score) >= 80:
            return True
    except (TypeError, ValueError):
        pass
    threat = str(inc.get("threat_type") or inc.get("type") or "").lower()
    if any(t in threat for t in _SUSPENDABLE_THREATS):
        return True
    title = str(inc.get("title") or inc.get("summary") or "").lower()
    if "injection" in title or "bruteforce" in title or "brute force" in title:
        return True
    return False


def _user_key(user: dict[str, Any]) -> str:
    uid = user.get("id") or user.get("user_id")
    if uid is not None:
        return f"id:{uid}"
    email = str(user.get("email") or user.get("user_email") or "").lower().strip()
    return f"email:{email}" if email else ""


def _merge_suspendable_entry(
    store: dict[str, dict[str, Any]],
    *,
    user_id: int | None,
    email: str | None,
    full_name: str | None,
    role: str | None,
    risk_score: int | float,
    reason: str,
    recommended_action: str,
    source: str,
) -> None:
    key = f"id:{user_id}" if user_id else (f"email:{email.lower()}" if email else "")
    if not key:
        return
    entry = store.get(key)
    if not entry:
        entry = {
            "id": user_id,
            "email": email or "—",
            "full_name": full_name or email or "—",
            "role": role or "—",
            "risk_score": risk_score,
            "reasons": [],
            "recommended_action": recommended_action or "monitor",
            "sources": [],
        }
        store[key] = entry
    if reason and reason not in entry["reasons"]:
        entry["reasons"].append(reason)
    if source not in entry["sources"]:
        entry["sources"].append(source)
    try:
        entry["risk_score"] = max(float(entry["risk_score"]), float(risk_score))
    except (TypeError, ValueError):
        pass
    if recommended_action in _SUSPENDABLE_ACTIONS:
        entry["recommended_action"] = recommended_action


def get_suspended_users(
    db: Session,
    admin: User,
    *,
    lang: str = "fr",
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    """Comptes réellement suspendus — jamais de fallback admin_accounts."""
    deadline = time.monotonic() + _FAST_DEADLINE
    results = execute_tool_plan(
        db, admin,
        [("get_users_summary", {"limit": 200, "status": "suspended"})],
        deadline=deadline,
        ui_language=lang,
    )
    payload = results[0]["response"] if results and results[0].get("ok") else {}
    raw_users = payload.get("users") if isinstance(payload.get("users"), list) else []
    suspended = filter_suspended_users(raw_users)
    tools = [r["name"] for r in results if r.get("ok")]
    return suspended, payload, tools


def get_suspendable_users(
    db: Session,
    admin: User,
    *,
    lang: str = "fr",
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    """Comptes à surveiller / suspension recommandée — distinct des suspendus."""
    deadline = time.monotonic() + _FAST_DEADLINE
    results = execute_tool_plan(
        db, admin,
        [
            ("get_users_summary", {"limit": 200}),
            ("get_security_alerts", {"limit": 30, "status": "open"}),
            ("analyze_suspicious_logs", {"hours": 24}),
        ],
        deadline=deadline,
        ui_language=lang,
    )
    tools = [r["name"] for r in results if r.get("ok")]

    users_by_id: dict[int, dict[str, Any]] = {}
    users_by_email: dict[str, dict[str, Any]] = {}
    security_payload: dict[str, Any] = {}
    logs_payload: dict[str, Any] = {}

    for r in results:
        payload = r.get("response") or {}
        if r["name"] == "get_users_summary" and r.get("ok"):
            for u in payload.get("users") or []:
                if not isinstance(u, dict):
                    continue
                if is_truly_suspended(u):
                    continue
                uid = u.get("id")
                if uid is not None:
                    users_by_id[int(uid)] = u
                em = str(u.get("email") or "").lower().strip()
                if em:
                    users_by_email[em] = u
        elif "security" in r["name"] and r.get("ok"):
            security_payload = payload
        elif "suspicious" in r["name"] and r.get("ok"):
            logs_payload = payload

    store: dict[str, dict[str, Any]] = {}

    incidents = (
        security_payload.get("incidents")
        or security_payload.get("sample")
        or []
    )
    for inc in incidents:
        if not isinstance(inc, dict) or not _incident_marks_suspendable(inc):
            continue
        uid = inc.get("user_id")
        email = str(inc.get("user_email") or inc.get("email") or "").lower().strip()
        user = users_by_id.get(int(uid)) if uid else None
        if not user and email:
            user = users_by_email.get(email)
        if user and is_truly_suspended(user):
            continue
        reason = str(
            inc.get("title") or inc.get("summary") or inc.get("threat_type") or "Alerte sécurité"
        )[:120]
        score = inc.get("score") or inc.get("risk_score") or 70
        _merge_suspendable_entry(
            store,
            user_id=int(uid) if uid else (user.get("id") if user else None),
            email=email or (user.get("email") if user else None),
            full_name=(inc.get("user_name") or (user.get("full_name") if user else None)),
            role=(user.get("role") if user else None),
            risk_score=score,
            reason=reason,
            recommended_action=str(inc.get("recommended_action") or "suspend_user"),
            source="security_alert",
        )

    for flag in logs_payload.get("risk_flags") or []:
        if not isinstance(flag, dict):
            continue
        uid = flag.get("user_id")
        user = users_by_id.get(int(uid)) if uid else None
        score = flag.get("risk_score") or 0
        if score < 2 and not flag.get("reasons"):
            continue
        if user and is_truly_suspended(user):
            continue
        reasons = flag.get("reasons") or ["Activité suspecte détectée"]
        _merge_suspendable_entry(
            store,
            user_id=int(uid) if uid else None,
            email=flag.get("email") or (user.get("email") if user else None),
            full_name=flag.get("full_name") or (user.get("full_name") if user else None),
            role=(user.get("role") if user else None),
            risk_score=score,
            reason="; ".join(str(r) for r in reasons[:2])[:120],
            recommended_action="suspend_user" if score >= 3 else "monitor",
            source="suspicious_logs",
        )

    suspendable = sorted(store.values(), key=lambda x: float(x.get("risk_score") or 0), reverse=True)
    meta = {
        "total": security_payload.get("total") or 0,
        "security_open": security_payload.get("open_count") or len(incidents),
    }
    return suspendable, meta, tools
