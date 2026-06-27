"""Phase 3d — composition Excel enrichi (séparé du message chat court)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.chat_export_service import generate_shipment_excel_from_fedex
from app.services.client_phase3.pdf_body_composer import resolve_tracking_for_pdf
from app.services.llm.fedex_context import compact_fedex_facts, fetch_fedex_tracking_data
from app.services.llm.providers import LlmProviderError, _extract_ollama_text, normalize_lang_code
from app.services.llm.prompts import language_lock_instruction

logger = logging.getLogger(__name__)

_VALID_LAYOUTS = frozenset({"summary_only", "summary_and_events", "events_table"})

_EXCEL_LAYOUT_SYSTEM = (
    "Tu choisis la STRUCTURE d'un export Excel FedEx Globex pour un client.\n"
    "Réponds UNIQUEMENT avec un objet JSON valide sur une ligne, sans markdown.\n"
    "Clés autorisées : layout (summary_only | summary_and_events | events_table).\n"
    "- summary_only : fiche synthèse une feuille\n"
    "- summary_and_events : synthèse + chronologie des scans (défaut recommandé pour un colis)\n"
    "- events_table : chronologie détaillée uniquement\n"
    "N'invente aucune donnée colis — choisis seulement la mise en page."
)


def short_excel_chat_reply(lang: str | None, *, doc_title: str | None = None) -> str:
    """Message chat court après génération Excel — sans répéter le contenu du fichier."""
    code = (lang or "fr").lower()[:2]
    if code == "en":
        base = "Your Excel file is ready — use the download link below."
        if doc_title:
            return f"{base}\n\nFile: {doc_title}"
        return base
    base = "Votre fichier Excel est prêt — utilisez le lien de téléchargement ci-dessous."
    if doc_title:
        return f"{base}\n\nFichier : {doc_title}"
    return base


def resolve_tracking_for_excel(
    message: str,
    last_bot_text: str | None,
    tracking_number: str | None,
) -> str | None:
    return resolve_tracking_for_pdf(message, last_bot_text, tracking_number)


def compose_excel_layout_fallback(fedex_payload: dict[str, Any]) -> str:
    """Layout déterministe par défaut."""
    shipment = fedex_payload.get("shipment") if isinstance(fedex_payload.get("shipment"), dict) else {}
    events = list(shipment.get("events") or fedex_payload.get("events") or [])
    if events:
        return "summary_and_events"
    return "summary_only"


def _normalize_layout(raw: str) -> str:
    text = (raw or "").strip().lower()
    if text in _VALID_LAYOUTS:
        return text
    match = re.search(
        r"\b(summary_only|summary_and_events|events_table)\b",
        text,
    )
    if match:
        return match.group(1)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            layout = str(data.get("layout") or "").strip().lower()
            if layout in _VALID_LAYOUTS:
                return layout
    except json.JSONDecodeError:
        pass
    return compose_excel_layout_fallback({})


def _call_ollama_layout(prompt: str) -> str:
    settings = get_settings()
    if not settings.llm_enabled:
        raise LlmProviderError("LLM désactivé (LLM_ENABLED=false).")
    base = settings.ollama_base_url.rstrip("/")
    body = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 64, "num_ctx": 1024},
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
        raise LlmProviderError("Réponse vide pour le layout Excel.")
    return text


def compose_excel_layout(
    message: str,
    fedex_payload: dict[str, Any],
    lang: str | None,
) -> str:
    """Ollama choisit la structure des feuilles ; repli déterministe si échec."""
    code = normalize_lang_code(lang)
    shipment = fedex_payload.get("shipment") if isinstance(fedex_payload.get("shipment"), dict) else {}
    facts = compact_fedex_facts(shipment) if shipment else str(fedex_payload.get("message") or "")
    system = f"{_EXCEL_LAYOUT_SYSTEM}\n{language_lock_instruction(code)}"
    prompt = (
        f"===SYSTEM===\n{system}\n"
        f"\n===FAITS FEDEX===\n{facts}\n"
        f"\n===DEMANDE===\n{(message or '').strip()}\n\n"
        'Réponds avec JSON uniquement, ex: {"layout":"summary_and_events"}'
    )
    try:
        raw = _call_ollama_layout(prompt)
        layout = _normalize_layout(raw)
        if layout not in _VALID_LAYOUTS:
            return compose_excel_layout_fallback(fedex_payload)
        return layout
    except LlmProviderError:
        logger.warning("Excel layout Ollama failed, using fallback", exc_info=True)
        return compose_excel_layout_fallback(fedex_payload)


def build_excel_body_for_shipment_turn(
    message: str,
    *,
    last_bot_text: str | None,
    chat_context: str | None,
    tracking_number: str | None,
    lang: str | None,
) -> tuple[bytes, str, str | None]:
    """
    Compose le fichier Excel pour followup / same_turn colis.
    Retourne (xlsx_bytes, filename, tracking_number_used).
    """
    _ = chat_context  # réservé extension future
    tn = resolve_tracking_for_excel(message, last_bot_text, tracking_number)
    code = normalize_lang_code(lang)

    if not tn:
        return b"", "", None

    fedex = fetch_fedex_tracking_data(tn)
    layout = compose_excel_layout(message, fedex, code)
    xlsx_bytes, filename = generate_shipment_excel_from_fedex(fedex, layout=layout, lang=code)
    return xlsx_bytes, filename, tn
