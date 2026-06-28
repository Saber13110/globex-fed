"""Exécution surveillance colis — Phase 6."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.chat_session_context import build_conversation_history_for_llm, resolve_tracking_for_message
from app.services.email_service import is_email_configured
from app.services.fedex_sandbox_whitelist import FedExSandboxWhitelistError
from app.services.shipment_watch_service import activate_client_shipment_watch, deactivate_user_watches


def _lang(ui_language: str | None, user: User) -> str:
    code = (ui_language or user.preferred_language or "fr").lower()[:2]
    return code if code in {"fr", "en", "ar"} else "fr"


def _limit_label(max_email_updates: int | None, lang: str) -> str:
    if max_email_updates is None:
        return "illimité" if lang != "en" else "unlimited"
    if lang == "en":
        return f"up to {max_email_updates} update email(s)"
    return f"jusqu'à {max_email_updates} mail(s) d'avancement"


def resolve_tracking_number(
    db: Session,
    *,
    session_id: int,
    user_id: int,
    message: str,
    answers: dict[str, Any],
    exclude_message_id: int | None,
) -> tuple[str | None, str]:
    explicit = str(answers.get("tracking_number") or "").strip()
    if explicit:
        return explicit, "message"
    history = build_conversation_history_for_llm(
        db,
        session_id=session_id,
        exclude_message_id=exclude_message_id,
        limit=4,
    )
    tn, source = resolve_tracking_for_message(
        db,
        session_id=session_id,
        user_id=user_id,
        message=message,
        conversation_history=history,
    )
    return tn, source


def execute_activate_watch(
    db: Session,
    user: User,
    *,
    session_id: int,
    message: str,
    answers: dict[str, Any],
    exclude_message_id: int | None,
    ui_language: str | None,
    assistant_intro: str = "",
) -> str:
    lang = _lang(ui_language, user)
    tn, _source = resolve_tracking_number(
        db,
        session_id=session_id,
        user_id=user.id,
        message=message,
        answers=answers,
        exclude_message_id=exclude_message_id,
    )
    if not tn:
        return (
            tracking_missing_reply(lang)
        )

    notify_email = bool(answers.get("notify_email", True))
    notify_in_app = bool(answers.get("notify_in_app", True))
    raw_max = answers.get("max_email_updates")
    max_email_updates: int | None
    if raw_max is None or raw_max == "":
        max_email_updates = None
    else:
        try:
            max_email_updates = min(max(int(raw_max), 1), 50)
        except (TypeError, ValueError):
            max_email_updates = None

    alert_type = str(answers.get("alert_type") or "all").strip().lower() or "all"

    try:
        outcome = activate_client_shipment_watch(
            db,
            user=user,
            tracking_number=tn,
            alert_type=alert_type,
            notify_email=notify_email,
            notify_in_app=notify_in_app,
            max_email_updates=max_email_updates if notify_email else None,
        )
    except FedExSandboxWhitelistError:
        if lang == "en":
            return f"Watch could not be activated for `{tn}` — number not allowed in FedEx sandbox."
        return (
            f"**Surveillance impossible** pour `{tn}`.\n\n"
            "Ce numéro n'est pas autorisé en environnement FedEx sandbox."
        )
    except Exception as exc:
        if lang == "en":
            return f"Could not activate watch for `{tn}`: {str(exc)[:120]}"
        return f"Impossible d'activer la surveillance pour `{tn}` : {str(exc)[:120]}"

    watch = outcome.get("watch")
    confirmation_sent = bool(outcome.get("confirmation_sent"))
    intro = (assistant_intro or "").strip()
    parts: list[str] = []
    if intro:
        parts.append(intro)
    if lang == "en":
        parts.append(f"**Watch active** for shipment `{tn}`.")
        if notify_email:
            email = (user.email or "").strip() or "your account email"
            parts.append(f"You will receive {_limit_label(max_email_updates, lang)} at **{email}**.")
            if confirmation_sent:
                parts.append("A confirmation email was just sent.")
            elif not is_email_configured():
                parts.append("_SMTP is not configured — progress emails will not be sent._")
        elif notify_in_app:
            parts.append("In-app alerts are enabled.")
    else:
        parts.append(f"**Surveillance active** pour le colis `{tn}`.")
        if notify_email:
            email = (user.email or "").strip() or "votre adresse e-mail"
            parts.append(
                f"Vous recevrez {_limit_label(max_email_updates, lang)} à **{email}**."
            )
            if confirmation_sent:
                parts.append("Un mail de confirmation vient d'être envoyé.")
            elif not is_email_configured():
                parts.append(
                    "_SMTP non configuré — les mails d'avancement ne partiront pas._"
                )
        elif notify_in_app:
            parts.append("Les alertes in-app sont activées.")
    if watch is not None and outcome.get("status"):
        parts.append(f"Statut actuel : {outcome.get('status')}.")
    return "\n\n".join(parts)


def execute_stop_watch(
    db: Session,
    user: User,
    *,
    answers: dict[str, Any],
    ui_language: str | None,
    assistant_intro: str = "",
) -> str:
    lang = _lang(ui_language, user)
    tn = str(answers.get("tracking_number") or "").strip() or None
    watches = deactivate_user_watches(
        db,
        user_id=user.id,
        tracking_number=tn,
        stop_all=True,
    )
    intro = (assistant_intro or "").strip()
    if lang == "en":
        if not watches:
            body = "No active shipment watch found on your account."
        elif tn:
            body = f"Watch stopped for shipment `{tn}`."
        else:
            body = f"Stopped {len(watches)} active shipment watch(es)."
    else:
        if not watches:
            body = "Aucune surveillance colis active trouvée sur votre compte."
        elif tn:
            body = f"Surveillance arrêtée pour le colis `{tn}`."
        else:
            body = f"Surveillance arrêtée pour {len(watches)} colis actif(s)."
    if intro:
        return f"{intro}\n\n{body}"
    return body


def tracking_missing_reply(lang: str) -> str:
    if lang == "en":
        return "Which FedEx tracking number would you like to watch?"
    return "Quel numéro de suivi FedEx souhaitez-vous surveiller ?"
