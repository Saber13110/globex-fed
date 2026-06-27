"""Agent sécurité admin — analyse et actions (manuel ou auto sur demande)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.activity_log_service import write_log
from app.services.security_ids_service import (
    get_or_create_policy,
    list_incidents,
    load_policy_rules,
    reactivate_user,
    run_ai_ids_scan,
    run_rule_scan,
    suspend_user,
)

logger = logging.getLogger(__name__)


def _parse_json_object(raw: str) -> dict[str, Any] | None:
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


def process_security_agent_message(
    db: Session,
    *,
    admin: User,
    message: str,
    ip_address: str = "",
) -> dict[str, Any]:
    """Interprète la demande admin et exécute les actions sécurité autorisées."""
    msg = message.strip()
    actions_taken: list[str] = []
    policy = get_or_create_policy(db)

    lowered = msg.lower()
    enable_auto = any(
        p in lowered
        for p in (
            "active le mode auto",
            "active la protection auto",
            "bloque automatiquement",
            "mode automatique",
            "auto mode",
            "enable auto",
        )
    )
    disable_auto = any(
        p in lowered
        for p in (
            "désactive le mode auto",
            "desactive le mode auto",
            "repasse en manuel",
            "mode manuel",
            "disable auto",
        )
    )

    if enable_auto and not disable_auto:
        policy.auto_mode_enabled = True
        policy.enabled_by_admin_id = admin.id
        from datetime import datetime, timezone

        policy.enabled_at = datetime.now(timezone.utc)
        db.commit()
        actions_taken.append("Mode automatique IDS activé")

    if disable_auto:
        policy.auto_mode_enabled = False
        db.commit()
        actions_taken.append("Mode automatique IDS désactivé")

    suspend_match = re.search(r"suspend(?:re)?\s+(?:user|utilisateur|compte)?\s*#?(\d+)", lowered)
    if suspend_match:
        uid = int(suspend_match.group(1))
        if suspend_user(db, uid, reason=f"Ordre admin : {admin.email}", actor_admin_id=admin.id):
            actions_taken.append(f"Utilisateur #{uid} suspendu")

    reactivate_match = re.search(r"r[eé]activ(?:er)?\s+(?:user|utilisateur|compte)?\s*#?(\d+)", lowered)
    if reactivate_match:
        uid = int(reactivate_match.group(1))
        if reactivate_user(db, uid, actor_admin_id=admin.id):
            actions_taken.append(f"Utilisateur #{uid} réactivé")

    if any(p in lowered for p in ("scanne", "scan ", "analyse les logs", "lance l'ids", "lance ids")):
        n_rules = run_rule_scan(db)
        actions_taken.append(f"Scan règles IDS : {n_rules} incident(s)")
        if "ia" in lowered or "gemini" in lowered or "ai" in lowered:
            n_ai = run_ai_ids_scan(db)
            actions_taken.append(f"Analyse IA : {n_ai} incident(s)")

    rows, total, open_count = list_incidents(db, status="open", limit=5, offset=0)
    incidents_ctx = "\n".join(
        f"- #{r.id} [{r.severity}] {r.title} (user={r.user_id})" for r in rows
    ) or "Aucun incident ouvert."

    policy = get_or_create_policy(db)
    rules = load_policy_rules(policy)
    context = (
        f"Politique IDS : auto_mode={policy.auto_mode_enabled}, règles={len(rules)}.\n"
        f"Incidents ouverts : {open_count} / {total} total.\n"
        f"Derniers incidents :\n{incidents_ctx}\n"
        f"Actions déjà exécutées cette requête : {actions_taken or 'aucune'}."
    )

    reply = _gemini_security_reply(msg, context, admin.preferred_language or "fr")
    if not reply:
        reply = _fallback_reply(actions_taken, open_count, policy.auto_mode_enabled)

    write_log(
        db,
        action="security.agent_query",
        message=msg[:200],
        category="security",
        level="INFO",
        actor_user_id=admin.id,
        ip_address=ip_address,
        metadata={"actions": actions_taken},
        commit=True,
    )

    return {
        "reply": reply,
        "actions_taken": actions_taken,
        "auto_mode_enabled": policy.auto_mode_enabled,
    }


def _gemini_security_reply(message: str, context: str, ui_language: str) -> str | None:
    try:
        from app.services.llm.providers import _gemini_generate
        from app.services.llm.prompts import language_lock_instruction

        lang_rule = language_lock_instruction(ui_language if ui_language in {"fr", "en", "ar"} else "fr")
        prompt = (
            f"{lang_rule}\n\n"
            "Tu es l'agent sécurité FedEx Globex pour l'administrateur.\n"
            "Réponds en français, ton professionnel et rassurant.\n"
            "Résume la situation sécurité et explique ce qui a été fait.\n"
            "Si mode auto désactivé, rappelle que les blocages nécessitent sa validation sauf ordre explicite.\n\n"
            f"CONTEXTE:\n{context}\n\n"
            f"DEMANDE ADMIN:\n{message}\n\n"
            "Réponse:"
        )
        return _gemini_generate(prompt, max_output_tokens=600, ui_language=ui_language)
    except Exception:
        logger.warning("Agent sécurité Gemini indisponible", exc_info=True)
        return None


def _fallback_reply(actions: list[str], open_count: int, auto_mode: bool) -> str:
    parts = [
        f"**Sécurité IDS** — {open_count} incident(s) ouvert(s).",
        f"Mode automatique : **{'activé' if auto_mode else 'désactivé'}** (l'admin garde le contrôle en mode manuel).",
    ]
    if actions:
        parts.append("Actions exécutées : " + "; ".join(actions))
    else:
        parts.append(
            "Je peux : activer/désactiver le mode auto, suspendre un compte (#id), "
            "lancer un scan IDS, ou analyser les incidents ouverts."
        )
    return "\n\n".join(parts)
