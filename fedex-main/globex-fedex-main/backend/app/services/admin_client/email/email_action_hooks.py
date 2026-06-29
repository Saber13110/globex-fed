"""Hooks e-mail après actions admin — Phase 2."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.admin_client.email.email_action_offer import (
    PendingActionEmailOffer,
    append_action_email_offer,
)
from app.services.admin_client.email.email_compose import compose_email_response
from app.services.admin_client.email.email_narrative import default_subject
from app.services.admin_client.email.email_service import build_user_email_draft
from app.services.admin_client.email.email_types import (
    EmailPlan,
    EmailProfile,
    EmailScenario,
    EmailTaskType,
    EmailToolError,
)
from app.services.admin_client.users.users_types import UsersTaskType


def scenario_for_users_task(task: UsersTaskType) -> EmailScenario | None:
    mapping = {
        UsersTaskType.user_suspend: EmailScenario.user_suspend,
        UsersTaskType.user_reactivate: EmailScenario.user_reactivate,
    }
    return mapping.get(task)


def scenario_for_ticket_action(action: str) -> EmailScenario | None:
    if action == "reply":
        return EmailScenario.ticket_reply
    if action == "resolve":
        return EmailScenario.ticket_resolved
    return None


def should_offer_email_after_users_action(task: UsersTaskType) -> bool:
    return task in {UsersTaskType.user_suspend, UsersTaskType.user_reactivate}


def should_offer_email_after_ticket_action(action: str) -> bool:
    return action in {"reply", "resolve"}


def build_admin_note_for_users_action(
    task: UsersTaskType,
    *,
    reason: str = "",
    lang: str = "fr",
) -> str:
    if task == UsersTaskType.user_suspend:
        if reason.strip():
            return reason.strip()
        return (
            "Votre compte a été temporairement suspendu par notre équipe support."
            if lang == "fr"
            else "Your account has been temporarily suspended by our support team."
        )
    if task == UsersTaskType.user_reactivate:
        return (
            "Votre compte a été réactivé. Vous pouvez vous reconnecter à la plateforme."
            if lang == "fr"
            else "Your account has been reactivated. You may sign in to the platform again."
        )
    return ""


def build_admin_note_for_ticket_action(
    action: str,
    *,
    ticket_subject: str = "",
    reply_body: str = "",
    lang: str = "fr",
) -> str:
    subj = (ticket_subject or "").strip()
    if action == "reply":
        body = (reply_body or "").strip()
        if body:
            return body
        if lang == "en":
            return f"We replied to your support ticket{f' « {subj} »' if subj else ''}."
        return f"Nous avons répondu à votre ticket support{f' « {subj} »' if subj else ''}."
    if action == "resolve":
        if lang == "en":
            return f"Your support ticket{f' « {subj} »' if subj else ''} has been marked as resolved."
        return f"Votre ticket support{f' « {subj} »' if subj else ''} a été marqué comme résolu."
    return ""


def enrich_reply_with_email_offer(
    reply: str,
    *,
    user_id: int,
    scenario: EmailScenario,
    admin_note: str = "",
    ticket_id: int | None = None,
    ticket_subject: str = "",
    recipient_email: str = "",
    lang: str = "fr",
) -> str:
    return append_action_email_offer(
        reply,
        user_id=user_id,
        scenario=scenario,
        admin_note=admin_note,
        ticket_id=ticket_id,
        ticket_subject=ticket_subject,
        recipient_email=recipient_email,
        lang=lang,
    )


def build_email_plan_from_offer(offer: PendingActionEmailOffer) -> EmailPlan:
    try:
        scenario = EmailScenario(offer.scenario)
    except ValueError:
        scenario = EmailScenario.custom
    return EmailPlan(
        task_type=EmailTaskType.send_user_email,
        profile=EmailProfile.DRAFT,
        user_id=offer.user_id,
        recipient_email=offer.recipient_email or None,
        admin_note=offer.admin_note,
        scenario=scenario,
        subject_hint=default_subject(scenario=scenario, lang="fr"),
        raw_matches=["action_email_offer"],
    )


def build_draft_turn_from_offer(
    db: Session,
    admin: User,
    offer: PendingActionEmailOffer,
    *,
    lang: str = "fr",
) -> dict[str, Any]:
    from app.services.admin_client.email.email_pipeline import add_backend_metadata

    plan = build_email_plan_from_offer(offer)
    plan.subject_hint = default_subject(scenario=plan.scenario, lang=lang)
    try:
        draft = build_user_email_draft(db, admin, plan, lang=lang)
    except EmailToolError as exc:
        return add_backend_metadata(
            {
                "reply": compose_email_response({}, plan, lang=lang, error_code=str(exc)),
                "intent": "email_error",
                "tracking_number": None,
                "shipment": None,
                "export_download": None,
                "agent_steps": [{"label": "action_email_offer", "status": "error", "detail": str(exc)}],
            },
            tool_used="action_email_offer",
            tools_called=["action_email_offer"],
            raw_data_received=False,
        )

    plan.profile = EmailProfile.CONFIRM
    reply = compose_email_response({}, plan, lang=lang, draft=draft)
    return add_backend_metadata(
        {
            "reply": reply,
            "intent": "email_draft",
            "tracking_number": None,
            "shipment": None,
            "export_download": None,
            "agent_steps": [{"label": "compose_user_email", "status": "done", "detail": draft.to}],
        },
        tool_used="compose_user_email",
        tools_called=["compose_user_email"],
        raw_data_received=True,
    )


def apply_post_action_email_hook(
    db: Session,
    admin: User,
    reply: str,
    *,
    user_id: int,
    scenario: EmailScenario,
    admin_note: str = "",
    ticket_id: int | None = None,
    ticket_subject: str = "",
    recipient_email: str = "",
    notify_inline: bool = False,
    lang: str = "fr",
) -> dict[str, Any] | str:
    """
    Après action admin : propose un e-mail ou passe directement au brouillon (notify_inline).
    Retourne un turn dict si brouillon inline, sinon la reply enrichie avec l'offre.
    """
    if notify_inline:
        offer = PendingActionEmailOffer(
            user_id=user_id,
            scenario=scenario.value,
            admin_note=admin_note,
            ticket_id=ticket_id,
            ticket_subject=ticket_subject,
            recipient_email=recipient_email,
        )
        draft_turn = build_draft_turn_from_offer(db, admin, offer, lang=lang)
        draft_turn["reply"] = (reply or "").strip() + "\n\n" + draft_turn["reply"]
        return draft_turn

    return enrich_reply_with_email_offer(
        reply,
        user_id=user_id,
        scenario=scenario,
        admin_note=admin_note,
        ticket_id=ticket_id,
        ticket_subject=ticket_subject,
        recipient_email=recipient_email,
        lang=lang,
    )
