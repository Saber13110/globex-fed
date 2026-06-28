"""Phase 3c — composition du corps PDF enrichi (séparé du message chat court)."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.llm.fedex_context import compact_fedex_facts, fetch_fedex_tracking_data
from app.services.llm.providers import LlmProviderError, _extract_ollama_text, normalize_lang_code
from app.services.llm.prompts import language_lock_instruction
from app.services.llm.tracking_extract import extract_tracking_number

logger = logging.getLogger(__name__)

_SHIPMENT_PDF_SYSTEM = (
    "Tu rédiges le CONTENU d'un document PDF professionnel pour un client FedEx Globex.\n"
    "Étapes internes (ne pas afficher) :\n"
    "1. Analyser la demande utilisateur.\n"
    "2. Choisir le format le plus adapté : rapport narratif, fiche synthèse, ou chronologie/tableau.\n"
    "3. Rédiger le document final.\n"
    "Règles strictes :\n"
    "- Texte BRUT uniquement : pas de markdown (** ## -), pas d'emojis, pas de liens.\n"
    "- INTERDIT : « je vais préparer », « patientez », « cliquez ici », ton conversationnel.\n"
    "- Utilise UNIQUEMENT les FAITS FEDEX fournis ; n'invente aucun statut, date ou lieu.\n"
    "- Longueur cible : 20 à 35 lignes pour un colis (sections courtes avec titres en MAJUSCULES).\n"
    "- Structure lisible : en-tête, résumé, détails, chronologie si pertinent."
)

_GENERIC_PDF_SYSTEM = (
    "Tu reformules le contenu suivant en document PDF professionnel FedEx Globex.\n"
    "Texte BRUT uniquement (pas de markdown, pas d'emojis, pas de liens).\n"
    "Garde les faits exacts ; n'invente rien. 15 à 30 lignes."
)


def short_pdf_chat_reply(lang: str | None, *, doc_title: str | None = None) -> str:
    """Message chat court après génération PDF — sans répéter le corps du document."""
    code = (lang or "fr").lower()[:2]
    if code == "en":
        base = "Your PDF document is ready — use the download link below."
        if doc_title:
            return f"{base}\n\nDocument: {doc_title}"
        return base
    base = "Votre document PDF est prêt — utilisez le lien de téléchargement ci-dessous."
    if doc_title:
        return f"{base}\n\nDocument : {doc_title}"
    return base


def strip_markdown_for_pdf(text: str | None) -> str:
    """Retire le markdown courant pour un rendu PDF texte plat."""
    if not text:
        return ""
    s = str(text).replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"```[\s\S]*?```", "", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"^#{1,6}\s+", "", s, flags=re.MULTILINE)
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"\*([^*]+)\*", r"\1", s)
    s = re.sub(r"__([^_]+)__", r"\1", s)
    s = re.sub(r"_([^_]+)_", r"\1", s)
    s = re.sub(r"^\s*[-*+]\s+", "- ", s, flags=re.MULTILINE)
    s = re.sub(r"^\s*\d+\.\s+", "", s, flags=re.MULTILINE)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def resolve_tracking_for_pdf(
    message: str,
    last_bot_text: str | None,
    tracking_number: str | None,
) -> str | None:
    """TN depuis param Phase 2, message utilisateur, ou dernière réponse bot."""
    if tracking_number and str(tracking_number).strip():
        return str(tracking_number).strip().upper()
    tn = extract_tracking_number(message or "")
    if tn:
        return tn
    if last_bot_text:
        return extract_tracking_number(last_bot_text)
    return None


def _shipment_dict_from_fedex(fedex_payload: dict[str, Any]) -> dict[str, Any]:
    if not fedex_payload.get("available"):
        return {}
    shipment = fedex_payload.get("shipment")
    if isinstance(shipment, dict) and shipment:
        return shipment
    return {
        k: fedex_payload[k]
        for k in (
            "tracking_number",
            "status",
            "current_location",
            "estimated_delivery",
            "actual_delivery",
            "recipient",
            "origin_location",
            "destination_location",
            "events",
        )
        if fedex_payload.get(k) is not None
    }


def compose_shipment_pdf_fallback(fedex_payload: dict[str, Any], lang: str | None) -> str:
    """Template déterministe ~25 lignes quand Ollama est indisponible."""
    code = (lang or "fr").lower()[:2]
    shipment = _shipment_dict_from_fedex(fedex_payload)
    tn = str(shipment.get("tracking_number") or fedex_payload.get("tracking_number") or "—")
    facts = compact_fedex_facts(shipment) if shipment else ""

    if code == "en":
        lines = [
            "FEDEX GLOBEX — SHIPMENT REPORT",
            "=" * 32,
            "",
            f"Tracking number: {tn}",
            "",
            "SUMMARY",
            "-" * 16,
        ]
        if facts:
            lines.extend(facts.splitlines())
        else:
            reason = fedex_payload.get("message") or "No FedEx data available."
            lines.append(reason)
        lines.extend(["", "EVENT TIMELINE", "-" * 16])
        events = list(shipment.get("events") or [])
        if events:
            for ev in events[:12]:
                if not isinstance(ev, dict):
                    continue
                at = ev.get("at") or ev.get("occurred_at") or "—"
                desc = ev.get("description") or "—"
                loc = ev.get("location") or ""
                suffix = f" — {loc}" if loc else ""
                lines.append(f"{at} — {desc}{suffix}")
        else:
            lines.append("No detailed scan events available.")
        lines.extend(["", "Document generated by FedEx Globex assistant."])
        return "\n".join(lines).strip()

    lines = [
        "FEDEX GLOBEX — RAPPORT DE SUIVI",
        "=" * 32,
        "",
        f"Numéro de suivi : {tn}",
        "",
        "SYNTHESE",
        "-" * 16,
    ]
    if facts:
        lines.extend(facts.splitlines())
    else:
        reason = fedex_payload.get("message") or "Aucune donnée FedEx disponible."
        lines.append(reason)
    lines.extend(["", "CHRONOLOGIE DES EVENEMENTS", "-" * 16])
    events = list(shipment.get("events") or [])
    if events:
        for ev in events[:12]:
            if not isinstance(ev, dict):
                continue
            at = ev.get("at") or ev.get("occurred_at") or "—"
            desc = ev.get("description") or "—"
            loc = ev.get("location") or ""
            suffix = f" — {loc}" if loc else ""
            lines.append(f"{at} — {desc}{suffix}")
    else:
        lines.append("Aucun scan détaillé disponible.")
    lines.extend(["", "Document généré par l'assistant FedEx Globex."])
    return "\n".join(lines).strip()


def _call_ollama_pdf_draft(prompt: str, *, num_predict: int = 512) -> str:
    settings = get_settings()
    if not settings.llm_enabled:
        raise LlmProviderError("LLM désactivé (LLM_ENABLED=false).")
    base = settings.ollama_base_url.rstrip("/")
    body = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.35, "num_predict": num_predict, "num_ctx": 2048},
    }
    timeout = httpx.Timeout(
        connect=5.0,
        read=settings.ollama_timeout_seconds,
        write=30.0,
        pool=5.0,
    )
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(f"{base}/api/generate", json=body)
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException as exc:
        raise LlmProviderError(f"Timeout Ollama ({settings.ollama_model})") from exc
    except Exception as exc:
        raise LlmProviderError(f"Échec Ollama : {exc}") from exc
    text = _extract_ollama_text(data).strip()
    if not text:
        raise LlmProviderError("Réponse vide pour le contenu PDF.")
    return text


def compose_shipment_pdf_body(
    message: str,
    fedex_payload: dict[str, Any],
    chat_context: str | None,
    lang: str | None,
) -> str:
    """Ollama rédige le corps PDF enrichi ; repli template si échec."""
    code = normalize_lang_code(lang)
    shipment = _shipment_dict_from_fedex(fedex_payload)
    facts = compact_fedex_facts(shipment) if shipment else (
        fedex_payload.get("message") or "Aucune donnée FedEx."
    )
    context_block = ""
    if chat_context and chat_context.strip():
        ctx = strip_markdown_for_pdf(chat_context.strip()[:800])
        if ctx:
            context_block = f"\n\n===CONTEXTE CHAT (reformuler, ne pas copier)===\n{ctx}\n"

    system = f"{_SHIPMENT_PDF_SYSTEM}\n{language_lock_instruction(code)}"
    prompt = (
        f"===SYSTEM===\n{system}\n"
        f"\n===FAITS FEDEX (source unique, ne rien inventer)===\n{facts}\n"
        f"{context_block}\n"
        f"===DEMANDE UTILISATEUR===\n{(message or '').strip()}\n\n"
        "Rédige le document PDF maintenant (texte brut, format adapté à la demande) :"
    )
    try:
        body = _call_ollama_pdf_draft(prompt)
        return strip_markdown_for_pdf(body)
    except LlmProviderError:
        logger.warning("Shipment PDF Ollama draft failed, using template fallback", exc_info=True)
        return compose_shipment_pdf_fallback(fedex_payload, code)


def compose_generic_pdf_body(
    message: str,
    source_text: str,
    lang: str | None,
) -> str:
    """Reformule un texte bot en document PDF quand pas de données FedEx structurées."""
    code = normalize_lang_code(lang)
    cleaned = strip_markdown_for_pdf(source_text)
    if not cleaned:
        return ""
    system = f"{_GENERIC_PDF_SYSTEM}\n{language_lock_instruction(code)}"
    prompt = (
        f"===SYSTEM===\n{system}\n"
        f"\n===CONTENU SOURCE===\n{cleaned[:2000]}\n"
        f"\n===DEMANDE===\n{(message or '').strip()}\n\n"
        "Rédige le document PDF :"
    )
    try:
        body = _call_ollama_pdf_draft(prompt, num_predict=384)
        return strip_markdown_for_pdf(body)
    except LlmProviderError:
        logger.warning("Generic PDF Ollama draft failed, using stripped source", exc_info=True)
        return cleaned


def build_pdf_body_for_shipment_turn(
    message: str,
    *,
    last_bot_text: str | None,
    chat_context: str | None,
    tracking_number: str | None,
    lang: str | None,
) -> tuple[str, str | None]:
    """
    Compose le corps PDF pour followup / same_turn colis.
    Retourne (pdf_body, tracking_number_used).
    """
    tn = resolve_tracking_for_pdf(message, last_bot_text, tracking_number)
    context = chat_context or last_bot_text

    if tn:
        fedex = fetch_fedex_tracking_data(tn)
        if fedex.get("available"):
            body = compose_shipment_pdf_body(message, fedex, context, lang)
            return body, tn
        fallback_shipment = {"tracking_number": tn, **fedex}
        body = compose_shipment_pdf_fallback(fallback_shipment, lang)
        return body, tn

    source = (chat_context or last_bot_text or "").strip()
    if source:
        body = compose_generic_pdf_body(message, source, lang)
        return body, None

    return "", None
