"""
Contexte FedEx pour le LLM — uniquement des données réelles du backend.
Ne jamais inventer de statut, date ou localisation.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from dataclasses import dataclass

from app.core.config import get_settings
from app.services import fedex_service
from app.services.fedex_sandbox_whitelist import (
    CLIENT_TRACKING_NOT_FOUND_HINT,
    FedExSandboxWhitelistError,
    SANDBOX_WHITELIST_MESSAGE,
)
from app.services.fedex_service import TrackingLookupError
from app.services.chat_shipment_reply import INTENT_MAP_TRACKING

logger = logging.getLogger(__name__)


def build_shipment_llm_context(
    *,
    tracking_number: str,
    shipment: dict[str, Any] | None = None,
    visibility_events: list[dict[str, Any]] | None = None,
    pod_info: dict[str, Any] | None = None,
    pod_available: bool = False,
    error_code: str | None = None,
    error_message: str | None = None,
    user_question_intent: str | None = None,
    conversation_mode: str = "first_lookup",
) -> str:
    """Construit le JSON injecté dans le prompt LLM après appel FedEx côté backend."""
    tn = tracking_number.strip().upper()
    payload: dict[str, Any] = {
        "tracking_number": tn,
        "available": shipment is not None and not error_code,
        "pod_available": pod_available,
        "conversation_mode": conversation_mode,
    }
    if user_question_intent:
        payload["user_question_intent"] = user_question_intent
    if user_question_intent == "follow_up_expand":
        payload["reply_instruction"] = (
            "L'utilisateur veut plus de détails. "
            "Réponds avec un ton humain et chaleureux ; apporte des informations NOUVELLES "
            "(historique, détails expéditeur/destinataire, carte…). "
            "Termine par UNE question de suggestion pour continuer la conversation."
        )
    elif user_question_intent == "delivery_eta":
        payload["reply_instruction"] = (
            "Question sur le délai ou la date d'arrivée. "
            "Réponds naturellement avec estimated_delivery et le statut actuel depuis FedEx. "
            "Rassure le client sur la situation. Ne redemande PAS le numéro de suivi. "
            "Termine par une suggestion (historique, localisation, carte, POD…)."
        )
    elif user_question_intent == "tabular_history":
        payload["reply_instruction"] = (
            "L'utilisateur demande un tableau. Le serveur insère le tableau vérifié (événements FedEx). "
            "Rédigez une intro humaine (2 à 3 phrases) qui répond à la demande tableau. "
            "Ne générez PAS le tableau Markdown vous-même — pas de lignes | --- | ni liste de scans inventés. "
            "Terminez par une courte suggestion (POD, carte, détails expéditeur…)."
        )
    elif user_question_intent == INTENT_MAP_TRACKING:
        payload["reply_instruction"] = (
            "Intention MAP_TRACKING : annonce la carte du trajet en langage naturel (2-4 phrases), "
            "par ex. « Voici le parcours de votre colis — la carte interactive s'affiche juste en dessous. » "
            "Ne liste pas tous les scans en texte (la carte le fait visuellement). "
            "Termine par une question de suggestion (tableau, POD, surveillance…)."
        )
    elif user_question_intent == "scan_history":
        payload["reply_instruction"] = (
            "L'utilisateur demande l'historique. "
            "Présente les scans de façon lisible (date, lieu, description) avec un ton humain. "
            "Termine par une suggestion (carte, POD, détails expéditeur…)."
        )
    elif conversation_mode == "follow_up":
        payload["reply_instruction"] = (
            "Question de suivi sur un colis déjà évoqué. "
            "Réponds à ce qui est demandé dans CE message avec le même ton conversationnel. "
            "Ne répète pas le statut, la localisation ni la date estimée sauf demande explicite. "
            "Termine toujours par une question de suggestion."
        )
    else:
        payload["reply_instruction"] = (
            "Première présentation du colis : accueille le client, résume statut / lieu / ETA "
            "comme un conseiller FedEx (4 à 6 phrases), puis propose 1 ou 2 pistes concrètes "
            "(historique, carte, preuve de livraison, surveillance…)."
        )
    if error_code:
        payload["reason"] = error_code
        payload["message"] = error_message or ""
        if error_code == "sandbox_whitelist_denied":
            payload["reply_instruction"] = (
                "Le numéro de suivi fourni n'existe pas dans FedEx (colis introuvable). "
                "Réponds comme un conseiller : aucun colis trouvé pour ce numéro, il est peut-être erroné. "
                "Demande poliment un numéro de suivi valide (12 à 14 chiffres). "
                "NE mentionne JAMAIS : sandbox, liste blanche, prompt injection, attaque, sécurité, API."
            )
        elif error_code == "fedex_not_found":
            payload["reply_instruction"] = (
                "FedEx ne reconnaît pas ce numéro de suivi. "
                "Réponds naturellement : colis introuvable, vérifiez le numéro ou réessayez plus tard. "
                "NE mentionne JAMAIS prompt injection ni attaque."
            )
        elif error_code == "fedex_unavailable":
            payload["reply_instruction"] = (
                "Le service FedEx est temporairement indisponible. "
                "Réponds honnêtement : impossible de récupérer le suivi pour le moment, propose de réessayer plus tard. "
                "NE mentionne JAMAIS : sandbox, liste blanche, API, prompt injection, attaque."
            )
    if shipment:
        view = {k: v for k, v in shipment.items() if k != "raw"}
        events = view.get("events")
        if isinstance(events, list) and len(events) > 12:
            view["events"] = events[:12]
        payload["shipment"] = view
        payload["status"] = shipment.get("status")
        payload["current_location"] = shipment.get("current_location")
        payload["estimated_delivery"] = shipment.get("estimated_delivery")
        payload["pod_download"] = (
            "Preuve de livraison disponible — le client peut la demander (PDF) ou l'obtenir via l'historique tracking."
            if pod_available
            else None
        )
    if visibility_events:
        payload["visibility_events"] = visibility_events[:6]
    if pod_info:
        payload["pod_info"] = pod_info
    return format_fedex_context_for_prompt(payload)


def fetch_fedex_tracking_data(tracking_number: str) -> dict[str, Any]:
    """
    Récupère les données FedEx pour le LLM (appel API backend).
  """
    settings = get_settings()
    tn = tracking_number.strip().upper()

    if not settings.fedex_enabled:
        logger.info("FedEx API désactivée (FEDEX_ENABLED=false) pour %s", tn)
        return {
            "available": False,
            "tracking_number": tn,
            "reason": "fedex_not_configured",
            "message": (
                "L'API FedEx n'est pas encore configurée sur ce serveur. "
                "Aucune donnée de suivi réelle n'est disponible pour le moment."
            ),
        }

    try:
        data = fedex_service.get_shipment(tn)
        view = {k: v for k, v in data.items() if k != "raw"}
        return {
            "available": True,
            "tracking_number": data.get("tracking_number", tn),
            "status": data.get("status"),
            "current_location": data.get("current_location"),
            "estimated_delivery": data.get("estimated_delivery"),
            "shipment": view,
        }
    except FedExSandboxWhitelistError:
        return {
            "available": False,
            "tracking_number": tn,
            "reason": "sandbox_whitelist_denied",
            "message": CLIENT_TRACKING_NOT_FOUND_HINT,
        }
    except TrackingLookupError as exc:
        logger.warning("FedEx lookup failed for %s: %s", tn, exc)
        return {
            "available": False,
            "tracking_number": tn,
            "reason": "fedex_not_found",
            "message": str(exc),
        }
    except Exception:
        logger.exception("FedEx API error for %s", tn)
        return {
            "available": False,
            "tracking_number": tn,
            "reason": "fedex_unavailable",
            "message": "Le service FedEx est temporairement indisponible.",
        }


def _json_prompt_default(value: Any) -> str:
    """Sérialise dates, Decimal, ORM, etc. sans faire échouer le prefetch FedEx."""
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    return str(value)


def format_fedex_context_for_prompt(fedex_payload: dict[str, Any]) -> str:
    """Sérialise le contexte FedEx pour injection dans le prompt LLM."""
    return json.dumps(
        fedex_payload,
        ensure_ascii=False,
        indent=2,
        default=_json_prompt_default,
    )


@dataclass
class ClientFedexLookup:
    """Résultat d'une recherche FedEx pour le portail client."""

    tracking_number: str | None
    fedex_context_json: str | None
    tracking_error_code: str | None
    llm_intent: str


def resolve_client_fedex_lookup(
    tracking_number: str,
    *,
    user_question_intent: str = "track_package",
    conversation_mode: str = "first_lookup",
) -> ClientFedexLookup:
    """
    Interroge FedEx côté serveur et construit le contexte LLM pour le client.
    Utilisé par le chat, l'agent GPT et l'agent classique.
    """
    tn = tracking_number.strip().upper()
    try:
        data = fedex_service.get_shipment(tn)
        ctx = build_shipment_llm_context(
            tracking_number=tn,
            shipment=data,
            user_question_intent=user_question_intent,
            conversation_mode=conversation_mode,
        )
        return ClientFedexLookup(
            tracking_number=tn,
            fedex_context_json=ctx,
            tracking_error_code=None,
            llm_intent=user_question_intent,
        )
    except FedExSandboxWhitelistError as exc:
        ctx = build_shipment_llm_context(
            tracking_number=exc.tracking_number,
            error_code="sandbox_whitelist_denied",
            error_message=CLIENT_TRACKING_NOT_FOUND_HINT,
            user_question_intent=user_question_intent,
        )
        return ClientFedexLookup(
            tracking_number=exc.tracking_number,
            fedex_context_json=ctx,
            tracking_error_code="sandbox_whitelist_denied",
            llm_intent="sandbox_whitelist_denied",
        )
    except TrackingLookupError as exc:
        ctx = build_shipment_llm_context(
            tracking_number=tn,
            error_code="fedex_not_found",
            error_message=str(exc),
            user_question_intent=user_question_intent,
        )
        return ClientFedexLookup(
            tracking_number=tn,
            fedex_context_json=ctx,
            tracking_error_code="fedex_not_found",
            llm_intent="fedex_not_found",
        )
    except Exception:
        logger.warning("FedEx lookup client échoué pour %s", tn, exc_info=True)
        ctx = build_shipment_llm_context(
            tracking_number=tn,
            error_code="fedex_unavailable",
            error_message="Le service FedEx est temporairement indisponible.",
            user_question_intent=user_question_intent,
        )
        return ClientFedexLookup(
            tracking_number=tn,
            fedex_context_json=ctx,
            tracking_error_code="fedex_unavailable",
            llm_intent="fedex_unavailable",
        )


def client_tracking_server_instruction(
    *,
    tracking_number: str,
    tracking_error_code: str | None,
) -> str:
    """Consigne serveur injectée quand le numéro est déjà connu et vérifié."""
    tn = tracking_number.strip().upper()
    if tracking_error_code in ("sandbox_whitelist_denied", "fedex_not_found", "fedex_unavailable"):
        return (
            f"Le client demande le suivi du colis {tn}. "
            "Le serveur a DÉJÀ interrogé FedEx : aucun colis trouvé pour ce numéro (voir FEDEX_DATA). "
            f"Répondez sur le numéro {tn} — ne redemandez JAMAIS le numéro de suivi. "
            "Dites clairement que ce colis n'existe pas ou que le numéro est invalide, "
            "puis proposez poliment un numéro FedEx valide (12 à 14 chiffres). "
            "Interdit : listes génériques des méthodes de suivi FedEx, jargon technique, prompt injection."
        )
    return (
        f"Le client demande le suivi du colis {tn}. "
        "Le serveur a DÉJÀ récupéré les données FedEx (voir FEDEX_DATA). "
        f"Répondez sur CE colis ({tn}) : statut, lieu, ETA. "
        "Ne redemandez pas le numéro. Si l'utilisateur demande l'outil fedex_track_package, "
        "les données FEDEX_DATA sont déjà la source de vérité."
    )
