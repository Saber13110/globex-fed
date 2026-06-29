"""DÉPRÉCIÉ — ne plus importer.

Ce module était une copie partielle du pipeline client de suivi colis. Il est remplacé
par le pipeline `admin_client` (`app.services.admin_client.pipeline.run_admin_client_turn`)
qui réutilise directement le flux client live (`_compute_phase2_reply`) via une session
miroir, et résout correctement le numéro de suivi en relance.

Conservé temporairement pour référence ; plus aucun appelant ne l'utilise.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.activity_log_service import write_log
from app.services.chat_shipment_reply import (
    build_shipment_reply,
    classify_shipment_question,
    shipment_card_display_flags,
    should_attach_shipment_card,
)
from app.services.fedex_sandbox_whitelist import CLIENT_TRACKING_NOT_FOUND_HINT
from app.services.llm.fedex_context import fetch_fedex_tracking_data
from app.services.llm.tracking_extract import extract_tracking_number
from app.services.proof_of_delivery_service import is_pod_available
from app.services.tracking_presenter import shipment_summary

logger = logging.getLogger(__name__)


def _lang_code(ui_language: str | None) -> str:
    return (ui_language or "fr").lower()[:2]


def _admin_tracking_error_reply(
    tracking_number: str,
    fedex_payload: dict[str, Any],
    ui_language: str | None,
) -> str:
    lang = _lang_code(ui_language)
    reason = fedex_payload.get("reason") or ""
    msg = fedex_payload.get("message") or CLIENT_TRACKING_NOT_FOUND_HINT
    if reason == "sandbox_whitelist_denied":
        msg = CLIENT_TRACKING_NOT_FOUND_HINT
    if lang == "en":
        return (
            f"I detected tracking number **{tracking_number}**, but I cannot confirm the real "
            f"package status without a response from FedEx.\n\n{msg}\n\n"
            "Please check the number (12–14 digits) or try again later."
        )
    return (
        f"J'ai détecté le numéro de suivi **{tracking_number}**, mais je ne peux pas confirmer "
        f"le statut réel du colis sans réponse de FedEx.\n\n{msg}\n\n"
        "Vérifiez le numéro (12 à 14 chiffres) ou réessayez plus tard."
    )


def _admin_error_shipment_card(tracking_number: str, reason: str) -> dict[str, Any] | None:
    if reason != "sandbox_whitelist_denied":
        return None
    tn = tracking_number.strip().upper()
    return {
        "tracking_number": tn,
        "sandbox_whitelist_denied": True,
        "status": None,
        "current_location": None,
        "estimated_delivery": None,
    }


def _admin_maybe_shipment_card(
    shipment_data: dict[str, Any],
    intent: str,
    *,
    pod_available: bool = False,
) -> dict[str, Any] | None:
    if not should_attach_shipment_card(
        intent=intent,
        tracking_source="message",
        pod_available=pod_available,
    ):
        return None
    flags = shipment_card_display_flags(intent)
    return shipment_summary(shipment_data, **flags)


def try_admin_shipment_turn(
    db: Session,
    admin: User,
    message: str,
    *,
    conversation_history: list[dict[str, str]] | None = None,
    ui_language: str = "fr",
    agent_mode: bool = False,
    ip_address: str = "",
    started: float | None = None,
) -> dict[str, Any] | None:
    """
    Suivi colis admin identique client : FedEx live + build_shipment_reply + shipment_summary.
    Retourne None si aucun numéro de suivi résolu.
    """
    t0 = started if started is not None else time.perf_counter()
    lang = _lang_code(ui_language)
    text = (message or "").strip()
    if not text:
        return None

    # Déprécié : résolution simplifiée (le pipeline admin_client utilise resolve_tracking_for_message).
    tracking_number = extract_tracking_number(text)
    if not tracking_number:
        return None

    fedex = fetch_fedex_tracking_data(tracking_number)
    if not fedex.get("available"):
        reason = str(fedex.get("reason") or "fedex_error")
        reply = _admin_tracking_error_reply(tracking_number, fedex, lang)
        shipment_for_admin = _admin_error_shipment_card(tracking_number, reason)
        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        write_log(
            db,
            action="globex_agent.chat",
            message=text[:120],
            category="admin",
            level="INFO",
            actor_user_id=admin.id,
            ip_address=ip_address,
            metadata={
                "agent_mode": agent_mode,
                "tools": ["fedex_track_package"],
                "orchestrator": "simple_bridge",
                "simple_mode": True,
                "intent": reason,
            },
        )
        db.commit()
        return {
            "reply": reply,
            "mode": "jarvis",
            "tools_used": ["fedex_track_package"],
            "agent_steps": [],
            "needs_approval": False,
            "approval_id": None,
            "approval_hint": None,
            "mission_id": None,
            "action_executed": False,
            "export_download": None,
            "llm_degraded": False,
            "intent": reason,
            "execution_time_ms": elapsed,
            "shipment": shipment_for_admin,
        }

    shipment_data = fedex.get("shipment") or {}
    pod_available = is_pod_available(shipment_data)
    reply, intent = build_shipment_reply(message, shipment_data)
    shipment_for_admin = _admin_maybe_shipment_card(
        shipment_data,
        intent,
        pod_available=pod_available,
    )

    elapsed = round((time.perf_counter() - t0) * 1000, 1)
    write_log(
        db,
        action="globex_agent.chat",
        message=text[:120],
        category="admin",
        level="INFO",
        actor_user_id=admin.id,
        ip_address=ip_address,
        metadata={
            "agent_mode": agent_mode,
            "tools": ["fedex_track_package"],
            "orchestrator": "simple_bridge",
            "simple_mode": True,
            "intent": intent,
            "tracking_number": tracking_number,
        },
    )
    db.commit()

    return {
        "reply": reply,
        "mode": "jarvis",
        "tools_used": ["fedex_track_package"],
        "agent_steps": [
            {
                "label": "fedex_track_package",
                "status": "done",
                "detail": json.dumps(
                    {
                        "tracking_number": tracking_number,
                        "status": shipment_data.get("status"),
                        "intent": intent,
                    },
                    ensure_ascii=False,
                )[:120],
            }
        ],
        "needs_approval": False,
        "approval_id": None,
        "approval_hint": None,
        "mission_id": None,
        "action_executed": False,
        "export_download": None,
        "llm_degraded": False,
        "intent": intent,
        "execution_time_ms": elapsed,
        "shipment": shipment_for_admin,
    }
