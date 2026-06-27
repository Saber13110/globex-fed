"""Soumission et validation des préférences IA utilisateur."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.preference_submission import PreferenceSubmission, PreferenceSubmissionStatus
from app.models.user import User
from app.schemas.preference import PreferenceSubmitRequest, UserPreferencesState
from app.schemas.preference_profile import PreferenceProfileStructured
from app.services.preference_notify_service import notify_admins_preference_submitted
from app.services.preference_profile import (
    compose_preference_text,
    profile_from_json,
    profile_from_payload,
    profile_to_json,
)
from app.services.prompt_guard_service import (
    RiskLevel,
    assess_preference_text,
    must_block_preferences,
    sanitize_style_hints,
)


def parse_risk_reasons(raw: str) -> list[str]:
    try:
        data = json.loads(raw or "[]")
        if isinstance(data, list):
            return [str(x) for x in data]
    except json.JSONDecodeError:
        pass
    return []


def _resolve_submit_text(payload: PreferenceSubmitRequest) -> tuple[str, PreferenceProfileStructured]:
    legacy = (payload.proposed_text or "").strip()
    if legacy and payload.tone is None and payload.cite_fedex is None and payload.short_answers is None:
        profile = PreferenceProfileStructured(free_notes=legacy[:300])
        return legacy, profile

    profile = profile_from_payload(
        {
            "tone": payload.tone,
            "cite_fedex": payload.cite_fedex if payload.cite_fedex is not None else True,
            "short_answers": payload.short_answers if payload.short_answers is not None else False,
            "free_notes": payload.free_notes or "",
        }
    )
    composed = compose_preference_text(profile)
    return composed, profile


def get_preferences_state(db: Session, user: User) -> UserPreferencesState:
    pending = db.scalar(
        select(PreferenceSubmission)
        .where(
            PreferenceSubmission.user_id == user.id,
            PreferenceSubmission.status == PreferenceSubmissionStatus.pending.value,
        )
        .order_by(PreferenceSubmission.created_at.desc())
        .limit(1)
    )
    last_rejected = db.scalar(
        select(PreferenceSubmission)
        .where(
            PreferenceSubmission.user_id == user.id,
            PreferenceSubmission.status == PreferenceSubmissionStatus.rejected.value,
        )
        .order_by(PreferenceSubmission.reviewed_at.desc())
        .limit(1)
    )
    active_structured = profile_from_json(user.preference_profile_json) or profile_from_json(
        user.response_preferences
    )
    pending_structured = profile_from_json(pending.structured_json) if pending else None

    return UserPreferencesState(
        active=user.response_preferences or "",
        active_structured=active_structured,
        pending=pending.proposed_text if pending else None,
        pending_structured=pending_structured,
        pending_id=pending.id if pending else None,
        pending_status=pending.status if pending else None,
        pending_risk_score=pending.risk_score if pending else None,
        pending_risk_reasons=parse_risk_reasons(pending.risk_reasons) if pending else [],
        rejection_note=last_rejected.rejection_note if last_rejected and last_rejected.rejection_note else None,
        submitted_at=pending.created_at if pending else None,
    )


def submit_user_preferences(db: Session, user: User, payload: PreferenceSubmitRequest) -> PreferenceSubmission:
    try:
        text, profile = _resolve_submit_text(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if not text.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Le texte des préférences est vide.")

    risk = assess_preference_text(text)
    reasons_json = json.dumps(risk.reasons, ensure_ascii=False)
    structured_json = profile_to_json(profile)

    if must_block_preferences(risk):
        row = PreferenceSubmission(
            user_id=user.id,
            proposed_text=text[:4000],
            structured_json=structured_json,
            status=PreferenceSubmissionStatus.auto_blocked.value,
            risk_score=risk.score,
            risk_reasons=reasons_json,
        )
        db.add(row)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Ces préférences ont été refusées par la politique de sécurité "
                f"(score {risk.score}). Révisez le ton et le style sans donner d'ordres au modèle."
            ),
        )

    for old in db.scalars(
        select(PreferenceSubmission).where(
            PreferenceSubmission.user_id == user.id,
            PreferenceSubmission.status == PreferenceSubmissionStatus.pending.value,
        )
    ).all():
        old.status = PreferenceSubmissionStatus.rejected.value
        old.rejection_note = "Remplacé par une nouvelle soumission."
        old.reviewed_at = datetime.now(timezone.utc)

    row = PreferenceSubmission(
        user_id=user.id,
        proposed_text=text[:4000],
        structured_json=structured_json,
        status=PreferenceSubmissionStatus.pending.value,
        risk_score=risk.score,
        risk_reasons=reasons_json,
    )
    db.add(row)
    db.flush()
    notify_admins_preference_submitted(db, submission=row, user=user)
    return row


def submit_user_preferences_legacy(db: Session, user: User, proposed_text: str) -> PreferenceSubmission:
    return submit_user_preferences(
        db, user, PreferenceSubmitRequest(proposed_text=proposed_text)
    )


def approve_submission(db: Session, submission_id: int, admin: User) -> PreferenceSubmission:
    row = db.get(PreferenceSubmission, submission_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Soumission introuvable.")
    if row.status != PreferenceSubmissionStatus.pending.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cette soumission n'est plus en attente.")

    risk = assess_preference_text(row.proposed_text)
    if must_block_preferences(risk) or risk.level == RiskLevel.block:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible d'approuver : contenu bloqué par la politique de sécurité.",
        )

    user = db.get(User, row.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable.")

    user.response_preferences = sanitize_style_hints(row.proposed_text, max_len=4000)
    user.preference_profile_json = row.structured_json or profile_to_json(PreferenceProfileStructured())
    row.status = PreferenceSubmissionStatus.approved.value
    row.reviewed_by = admin.id
    row.reviewed_at = datetime.now(timezone.utc)
    db.add(user)
    db.add(row)
    return row


def reject_submission(
    db: Session, submission_id: int, admin: User, note: str | None = None
) -> PreferenceSubmission:
    row = db.get(PreferenceSubmission, submission_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Soumission introuvable.")
    if row.status != PreferenceSubmissionStatus.pending.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cette soumission n'est plus en attente.")

    row.status = PreferenceSubmissionStatus.rejected.value
    row.reviewed_by = admin.id
    row.reviewed_at = datetime.now(timezone.utc)
    row.rejection_note = (note or "").strip()[:500]
    db.add(row)
    return row


def validate_admin_active_preferences(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""
    risk = assess_preference_text(cleaned)
    if must_block_preferences(risk):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contenu refusé par la politique de sécurité. Utilisez uniquement des indications de style.",
        )
    return sanitize_style_hints(cleaned, max_len=4000)
