"""IDS sécurité : incidents, règles, notifications admin, actions automatiques."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.activity_log import ActivityLog
from app.models.security_incident import SecurityIncident
from app.models.security_policy import DEFAULT_RULES_JSON, SecurityPolicy
from app.models.user import User, UserRole, UserStatus
from app.models.user_session import UserSession
from app.services.activity_log_service import write_log
from app.services.notifications_service import _upsert as upsert_platform_notification

logger = logging.getLogger(__name__)

INCIDENT_OPEN = "open"
INCIDENT_ACK = "acknowledged"
INCIDENT_RESOLVED = "resolved"
INCIDENT_FALSE_POSITIVE = "false_positive"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_or_create_policy(db: Session) -> SecurityPolicy:
    row = db.get(SecurityPolicy, 1)
    if row is None:
        settings = get_settings()
        row = SecurityPolicy(
            id=1,
            auto_mode_enabled=settings.security_auto_mode_default,
            rules_json=DEFAULT_RULES_JSON,
            ai_ids_enabled=settings.security_ids_ai_enabled,
        )
        db.add(row)
        db.flush()
    return row


def load_policy_rules(policy: SecurityPolicy) -> list[dict[str, Any]]:
    try:
        data = json.loads(policy.rules_json or "[]")
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return json.loads(DEFAULT_RULES_JSON)


def create_incident(
    db: Session,
    *,
    dedupe_key: str,
    source: str,
    threat_type: str,
    severity: str,
    score: int,
    title: str,
    summary: str,
    user_id: int | None = None,
    ip_address: str = "",
    evidence: dict[str, Any] | None = None,
    recommended_action: str = "monitor",
    auto_eligible: bool = False,
    commit: bool = True,
) -> SecurityIncident | None:
    """Crée un incident si la clé de déduplication n'existe pas déjà (ouverte)."""
    existing = db.scalar(
        select(SecurityIncident.id).where(
            SecurityIncident.dedupe_key == dedupe_key,
            SecurityIncident.status.in_((INCIDENT_OPEN, INCIDENT_ACK)),
        )
    )
    if existing:
        return None

    row = SecurityIncident(
        dedupe_key=dedupe_key,
        user_id=user_id,
        ip_address=(ip_address or "")[:64],
        source=source[:32],
        threat_type=threat_type[:64],
        severity=severity[:16],
        score=min(max(score, 0), 100),
        status=INCIDENT_OPEN,
        title=title[:200],
        summary=summary[:4000],
        evidence_json=json.dumps(evidence or {}, ensure_ascii=False)[:8000],
        recommended_action=recommended_action[:64],
        auto_eligible=auto_eligible,
    )
    db.add(row)
    db.flush()
    _notify_admins_incident(db, row)
    write_log(
        db,
        action="security.incident_created",
        message=title[:500],
        category="security",
        level="WARNING" if severity in ("high", "critical") else "INFO",
        user_id=user_id,
        ip_address=ip_address,
        metadata={"incident_id": row.id, "threat_type": threat_type, "score": score},
    )
    if commit:
        db.commit()
        db.refresh(row)
    return row


def _notify_admins_incident(db: Session, incident: SecurityIncident) -> None:
    user = db.get(User, incident.user_id) if incident.user_id else None
    user_label = user.email if user else "—"
    priority = "critical" if incident.severity == "critical" else (
        "high" if incident.severity == "high" else "normal"
    )
    upsert_platform_notification(
        db,
        external_key=f"sec-inc-{incident.id}",
        category="incidents",
        title=incident.title,
        message=f"{incident.summary[:300]} — {user_label}",
        priority=priority,
        icon="shield",
        action_label="Examiner",
        action_type="security_incident",
        action_ref=str(incident.id),
    )


def record_prompt_guard_event(
    db: Session,
    *,
    user_id: int | None,
    ip_address: str,
    score: int,
    reasons: list[str],
    level: str,
    message_preview: str = "",
    blocked: bool = False,
) -> SecurityIncident | None:
    if not get_settings().security_ids_enabled:
        return None
    severity = "high" if blocked or score >= 70 else ("medium" if score >= 40 else "low")
    if severity == "low":
        return None

    if user_id:
        write_log(
            db,
            action="security.attack_attempt",
            message=f"Tentative d'attaque (score {score}) — {message_preview[:100]}",
            category="security",
            level="WARNING",
            user_id=user_id,
            ip_address=ip_address,
            metadata={"reasons": reasons, "blocked": blocked, "score": score},
            commit=False,
        )
        db.flush()
        _maybe_notify_admin_block_user(db, user_id)

    bucket = _now().strftime("%Y%m%d%H")
    preview_key = sha256((message_preview or "attack").encode("utf-8")).hexdigest()[:12]
    dedupe = f"prompt-{user_id or 0}-{preview_key}-{bucket}"
    title = "Tentative de prompt injection bloquée" if blocked else "Tentative de prompt injection suspecte"
    summary = (
        f"Score {score} — motifs : {', '.join(reasons[:5]) or '—'}. "
        f"Extrait : {message_preview[:120]}"
    )
    recommended = "suspend_user" if blocked and score >= 80 else "monitor"
    if user_id:
        attempts = _count_user_attack_attempts(db, user_id)
        if attempts > get_settings().security_admin_notify_after_attempts:
            recommended = "suspend_user"

    inc = create_incident(
        db,
        dedupe_key=dedupe,
        source="prompt_guard",
        threat_type="prompt_injection",
        severity=severity,
        score=score,
        title=title,
        summary=summary,
        user_id=user_id,
        ip_address=ip_address,
        evidence={"reasons": reasons, "level": level, "blocked": blocked, "preview": message_preview[:200]},
        recommended_action=recommended,
        auto_eligible=blocked,
        commit=False,
    )
    db.commit()
    if inc:
        db.refresh(inc)
    return inc


def _count_user_attack_attempts(db: Session, user_id: int) -> int:
    settings = get_settings()
    since = _now() - timedelta(hours=max(1, int(settings.security_admin_notify_window_hours or 24)))
    return int(
        db.scalar(
            select(func.count())
            .select_from(ActivityLog)
            .where(
                ActivityLog.user_id == user_id,
                ActivityLog.action == "security.attack_attempt",
                ActivityLog.created_at >= since,
            )
        )
        or 0
    )


def _maybe_notify_admin_block_user(db: Session, user_id: int) -> None:
    """Après > N tentatives, notifie l'admin pour suspension manuelle du compte."""
    settings = get_settings()
    threshold = max(1, int(settings.security_admin_notify_after_attempts or 2))
    attempts = _count_user_attack_attempts(db, user_id)
    if attempts <= threshold:
        return

    user = db.get(User, user_id)
    if user is None or user.role == UserRole.admin.value or user.status == UserStatus.suspended.value:
        return

    window_h = int(settings.security_admin_notify_window_hours or 24)
    title = f"Action requise : bloquer {user.email}"
    message = (
        f"{attempts} tentatives d'attaque détectées en {window_h} h "
        f"({user.full_name} — {user.email}). "
        f"Suspendez manuellement ce compte depuis Sécurité IDS ou Utilisateurs."
    )
    external_key = f"sec-block-recommend-u{user_id}"
    from app.models.platform_notification import PlatformNotification

    row = db.scalar(
        select(PlatformNotification).where(PlatformNotification.external_key == external_key)
    )
    if row is None:
        upsert_platform_notification(
            db,
            external_key=external_key,
            category="incidents",
            title=title,
            message=message,
            priority="critical",
            icon="shield",
            action_label="Suspendre",
            action_type="security_suspend_user",
            action_ref=str(user_id),
        )
    else:
        row.title = title
        row.message = message
        row.priority = "critical"
        row.is_read = False
        row.action_label = "Suspendre"
        row.action_type = "security_suspend_user"
        row.action_ref = str(user_id)

    create_incident(
        db,
        dedupe_key=f"block-recommend-u{user_id}",
        source="rule_engine",
        threat_type="repeated_prompt_injection",
        severity="critical",
        score=min(70 + attempts * 5, 100),
        title=f"{attempts} tentatives d'attaque — suspension recommandée",
        summary=message,
        user_id=user_id,
        evidence={"attempt_count": attempts, "threshold": threshold},
        recommended_action="suspend_user",
        auto_eligible=False,
        commit=False,
    )
    write_log(
        db,
        action="security.admin_block_recommended",
        message=f"Admin alerté : bloquer {user.email} ({attempts} tentatives)",
        category="security",
        level="CRITICAL",
        user_id=user_id,
        metadata={"attempt_count": attempts, "threshold": threshold},
        commit=False,
    )


def _count_logs(
    db: Session,
    *,
    action: str,
    since: datetime,
    user_id: int | None = None,
    ip_address: str | None = None,
) -> int:
    stmt = select(func.count()).select_from(ActivityLog).where(
        ActivityLog.action == action,
        ActivityLog.created_at >= since,
    )
    if user_id is not None:
        stmt = stmt.where(ActivityLog.user_id == user_id)
    if ip_address:
        stmt = stmt.where(ActivityLog.ip_address == ip_address)
    return int(db.scalar(stmt) or 0)


def scan_recent_suspicious_chat_logs(db: Session) -> int:
    """Analyse rétroactive des messages chat récents (filet de sécurité)."""
    from app.services.prompt_guard_service import RiskLevel, assess_user_message

    since = _now() - timedelta(minutes=45)
    rows = list(
        db.scalars(
            select(ActivityLog)
            .where(
                ActivityLog.action.in_(("chat.user_message", "security.chat_probe")),
                ActivityLog.created_at >= since,
            )
            .order_by(ActivityLog.created_at.desc())
            .limit(80)
        ).all()
    )
    created = 0
    for row in rows:
        text = (row.message or "").strip()
        if text.lower().startswith("prompt :"):
            text = text.split(":", 1)[1].strip()
        if not text:
            continue
        risk = assess_user_message(text)
        if risk.level == RiskLevel.ok:
            continue
        preview_key = sha256(text[:200].encode("utf-8")).hexdigest()[:12]
        dedupe = f"chat-log-{row.id}-{preview_key}"
        inc = create_incident(
            db,
            dedupe_key=dedupe,
            source="rule_engine",
            threat_type="data_exfiltration"
            if any("code" in r or "secret" in r for r in risk.reasons)
            else "prompt_injection",
            severity="high" if risk.level.value == "block" else "medium",
            score=risk.score,
            title="Message chat suspect détecté (scan journaux)",
            summary=f"Score {risk.score} — {', '.join(risk.reasons[:5])}. Extrait : {text[:120]}",
            user_id=row.user_id,
            ip_address=row.ip_address or "",
            evidence={"log_id": row.id, "reasons": risk.reasons, "message": text[:300]},
            recommended_action="suspend_user" if risk.score >= 80 else "monitor",
            auto_eligible=risk.score >= 80,
            commit=False,
        )
        if inc:
            created += 1
    if created:
        db.commit()
    return created


def run_rule_scan(db: Session) -> int:
    """Applique les règles IDS sur activity_logs. Retourne le nombre d'incidents créés."""
    if not get_settings().security_ids_enabled:
        return 0

    created = scan_recent_suspicious_chat_logs(db)
    policy = get_or_create_policy(db)
    rules = load_policy_rules(policy)
    now = _now()
    hour_ago = now - timedelta(hours=1)
    quarter_ago = now - timedelta(minutes=15)

    user_rows = db.scalars(
        select(ActivityLog.user_id)
        .where(
            ActivityLog.action == "security.prompt_blocked",
            ActivityLog.created_at >= hour_ago,
            ActivityLog.user_id.isnot(None),
        )
        .distinct()
    ).all()
    for uid in user_rows:
        if uid is None:
            continue
        count = _count_logs(db, action="security.prompt_blocked", since=hour_ago, user_id=uid)
        for rule in rules:
            if rule.get("trigger") != "prompt_blocked_count_1h":
                continue
            threshold = int(rule.get("threshold") or 1)
            if count < threshold:
                continue
            action = rule.get("action") or "alert_only"
            dedupe = f"rule-prompt-1h-u{uid}-t{threshold}"
            inc = create_incident(
                db,
                dedupe_key=dedupe,
                source="rule_engine",
                threat_type="prompt_injection_burst",
                severity="high" if count >= 5 else "medium",
                score=min(60 + count * 5, 100),
                title=f"{count} prompts bloqués en 1 h (utilisateur #{uid})",
                summary=f"Seuil {threshold} dépassé — action recommandée : {action}.",
                user_id=uid,
                evidence={"count": count, "rule": rule},
                recommended_action=action,
                auto_eligible=action == "suspend_user",
                commit=False,
            )
            if inc:
                created += 1
                if policy.auto_mode_enabled and action == "suspend_user":
                    suspend_user(db, uid, reason=f"IDS auto : {count} prompts bloqués/1h", actor_admin_id=None)

    ip_rows = db.scalars(
        select(ActivityLog.ip_address)
        .where(
            ActivityLog.action.in_(("security.prompt_blocked", "auth.login_failed")),
            ActivityLog.created_at >= hour_ago,
            ActivityLog.ip_address != "",
        )
        .distinct()
    ).all()
    for ip in ip_rows:
        if not ip:
            continue
        count = _count_logs(db, action="security.prompt_blocked", since=hour_ago, ip_address=ip)
        if count >= 5:
            dedupe = f"rule-prompt-ip-{ip}-{hour_ago.strftime('%Y%m%d%H')}"
            if create_incident(
                db,
                dedupe_key=dedupe,
                source="rule_engine",
                threat_type="prompt_injection_ip",
                severity="high",
                score=75,
                title=f"Activité suspecte depuis {ip}",
                summary=f"{count} prompts bloqués depuis cette IP en 1 h.",
                ip_address=ip,
                evidence={"count": count, "ip": ip},
                recommended_action="monitor",
                auto_eligible=False,
                commit=False,
            ):
                created += 1

    fail_ips = db.scalars(
        select(ActivityLog.ip_address)
        .where(ActivityLog.action == "auth.login_failed", ActivityLog.created_at >= quarter_ago)
        .distinct()
    ).all()
    for ip in fail_ips:
        if not ip:
            continue
        fails = _count_logs(db, action="auth.login_failed", since=quarter_ago, ip_address=ip)
        for rule in rules:
            if rule.get("trigger") != "login_failures_ip_15m":
                continue
            threshold = int(rule.get("threshold") or 8)
            if fails < threshold:
                continue
            dedupe = f"rule-login-ip-{ip}-{quarter_ago.strftime('%Y%m%d%H%M')}"
            if create_incident(
                db,
                dedupe_key=dedupe,
                source="rule_engine",
                threat_type="brute_force",
                severity="medium",
                score=min(50 + fails * 3, 95),
                title=f"Tentatives de connexion suspectes ({ip})",
                summary=f"{fails} échecs de connexion en 15 min.",
                ip_address=ip,
                evidence={"fail_count": fails},
                recommended_action="monitor",
                auto_eligible=False,
                commit=False,
            ):
                created += 1

    db.commit()
    return created


def run_ai_ids_scan(db: Session) -> int:
    """Analyse IA des logs récents suspects (Gemini)."""
    settings = get_settings()
    policy = get_or_create_policy(db)
    if not settings.security_ids_enabled or not policy.ai_ids_enabled or not settings.llm_enabled:
        return 0

    since = _now() - timedelta(hours=2)
    rows = list(
        db.scalars(
            select(ActivityLog)
            .where(
                ActivityLog.created_at >= since,
                or_(
                    ActivityLog.category == "security",
                    ActivityLog.level.in_(("WARNING", "ERROR", "CRITICAL")),
                    ActivityLog.action.like("security.%"),
                ),
            )
            .order_by(ActivityLog.created_at.desc())
            .limit(40)
        ).all()
    )
    if len(rows) < 3:
        return 0

    lines = []
    for r in rows:
        lines.append(
            f"- [{r.created_at.isoformat() if r.created_at else ''}] "
            f"user={r.user_id} ip={r.ip_address} action={r.action} level={r.level} msg={r.message[:100]}"
        )
    logs_text = "\n".join(lines)

    prompt = (
        "Tu es un analyste SOC. Analyse ces journaux d'une plateforme FedEx chatbot.\n"
        "Réponds UNIQUEMENT en JSON valide :\n"
        '{"threat_detected":true|false,"threat_level":"low|medium|high|critical",'
        '"attack_type":"prompt_injection|brute_force|abuse|none",'
        '"summary":"phrase en français","recommended_action":"monitor|alert|suspend_user",'
        '"confidence":0-100,"affected_user_ids":[...]}\n\n'
        f"LOGS:\n{logs_text}"
    )
    try:
        from app.services.llm.providers import _gemini_generate

        raw = _gemini_generate(prompt, max_output_tokens=512, ui_language="fr")
    except Exception:
        logger.warning("IDS IA Gemini indisponible", exc_info=True)
        return 0

    if not raw:
        return 0

    data = _parse_json_object(raw)
    if not data or not data.get("threat_detected"):
        return 0

    threat_level = str(data.get("threat_level") or "medium")
    if threat_level == "low":
        return 0

    bucket = _now().strftime("%Y%m%d%H")
    dedupe = f"ai-ids-{bucket}"
    summary = str(data.get("summary") or "Analyse IA : activité suspecte détectée.")
    user_ids = data.get("affected_user_ids") if isinstance(data.get("affected_user_ids"), list) else []
    uid = int(user_ids[0]) if user_ids else None
    recommended = str(data.get("recommended_action") or "alert")

    inc = create_incident(
        db,
        dedupe_key=dedupe,
        source="ai_ids",
        threat_type=str(data.get("attack_type") or "unknown"),
        severity=threat_level,
        score=int(data.get("confidence") or 70),
        title="Analyse IA — menace détectée",
        summary=summary,
        user_id=uid,
        evidence={"ai_analysis": data, "log_count": len(rows)},
        recommended_action=recommended,
        auto_eligible=recommended == "suspend_user",
        commit=True,
    )
    if inc and policy.auto_mode_enabled and recommended == "suspend_user" and uid:
        suspend_user(db, uid, reason="IDS IA auto", actor_admin_id=None)
        return 1
    return 1 if inc else 0


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    import re

    text = (raw or "").strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def suspend_user(
    db: Session,
    user_id: int,
    *,
    reason: str,
    actor_admin_id: int | None,
) -> bool:
    user = db.get(User, user_id)
    if user is None or user.role == UserRole.admin.value:
        return False
    if user.status == UserStatus.suspended.value:
        return False

    user.status = UserStatus.suspended.value
    for sess in db.scalars(select(UserSession).where(UserSession.user_id == user_id)).all():
        sess.is_active = False

    write_log(
        db,
        action="security.user_suspended",
        message=f"Compte suspendu : {user.email} — {reason[:200]}",
        category="security",
        level="WARNING",
        user_id=user_id,
        actor_user_id=actor_admin_id,
        metadata={"reason": reason[:500]},
        commit=False,
    )
    upsert_platform_notification(
        db,
        external_key=f"sec-suspend-{user_id}-{int(_now().timestamp())}",
        category="incidents",
        title="Compte suspendu",
        message=f"{user.email} — {reason[:150]}",
        priority="high",
        icon="shield",
        action_type="user",
        action_ref=str(user_id),
    )
    db.commit()
    return True


def reactivate_user(db: Session, user_id: int, *, actor_admin_id: int) -> bool:
    user = db.get(User, user_id)
    if user is None:
        return False
    user.status = UserStatus.active.value
    write_log(
        db,
        action="security.user_reactivated",
        message=f"Compte réactivé : {user.email}",
        category="security",
        level="INFO",
        user_id=user_id,
        actor_user_id=actor_admin_id,
        commit=True,
    )
    return True


def list_incidents(
    db: Session,
    *,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[SecurityIncident], int, int]:
    stmt = select(SecurityIncident)
    count_stmt = select(func.count()).select_from(SecurityIncident)
    if status and status != "all":
        stmt = stmt.where(SecurityIncident.status == status)
        count_stmt = count_stmt.where(SecurityIncident.status == status)
    total = int(db.scalar(count_stmt) or 0)
    open_count = int(
        db.scalar(
            select(func.count()).select_from(SecurityIncident).where(
                SecurityIncident.status.in_((INCIDENT_OPEN, INCIDENT_ACK))
            )
        )
        or 0
    )
    rows = list(
        db.scalars(
            stmt.order_by(SecurityIncident.created_at.desc()).limit(limit).offset(offset)
        ).all()
    )
    return rows, total, open_count


def resolve_incident(
    db: Session,
    incident_id: int,
    *,
    status: str,
    admin_id: int,
    note: str = "",
) -> SecurityIncident | None:
    row = db.get(SecurityIncident, incident_id)
    if row is None:
        return None
    if status not in (INCIDENT_ACK, INCIDENT_RESOLVED, INCIDENT_FALSE_POSITIVE):
        return None
    row.status = status
    row.resolved_by_admin_id = admin_id
    row.resolution_note = (note or "")[:2000]
    row.resolved_at = _now()
    db.commit()
    db.refresh(row)
    return row


def incident_to_read(db: Session, row: SecurityIncident) -> dict[str, Any]:
    user = db.get(User, row.user_id) if row.user_id else None
    try:
        evidence = json.loads(row.evidence_json or "{}")
    except json.JSONDecodeError:
        evidence = {}
    return {
        "id": row.id,
        "user_id": row.user_id,
        "user_name": user.full_name if user else None,
        "user_email": user.email if user else None,
        "user_status": user.status if user else None,
        "ip_address": row.ip_address,
        "source": row.source,
        "threat_type": row.threat_type,
        "severity": row.severity,
        "score": row.score,
        "status": row.status,
        "title": row.title,
        "summary": row.summary,
        "evidence": evidence,
        "recommended_action": row.recommended_action,
        "auto_eligible": row.auto_eligible,
        "created_at": row.created_at,
        "resolved_at": row.resolved_at,
        "resolution_note": row.resolution_note or "",
    }
