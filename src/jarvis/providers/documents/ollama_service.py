from __future__ import annotations

import logging
from typing import Any

import httpx

from jarvis.kernel.settings import settings

logger = logging.getLogger(__name__)

DOCUMENT_QA_SYSTEM = (
    "Tu es un assistant local. Réponds uniquement à partir du contexte fourni. "
    "Si l'information n'est pas présente dans le contexte, dis clairement que tu ne peux pas le confirmer. "
    "Ne devine pas. Pour les tableaux, réponds de manière structurée. "
    "Pour les PDF, cite si possible la page. "
    "Pour les Excel, cite la feuille ou les colonnes utilisées."
)


def _build_user_message(question: str, context: dict[str, Any]) -> str:
    file_name = context.get("file_name") or "document"
    file_type = context.get("file_type") or ""
    extracted = (context.get("extracted_text") or "").strip()
    warnings = context.get("warnings") or []
    metadata = context.get("metadata") or {}

    lines = [
        f"DOCUMENT : {file_name} ({file_type})",
        f"MÉTADONNÉES : {metadata}",
    ]
    if warnings:
        lines.append("AVERTISSEMENTS : " + " | ".join(str(w) for w in warnings))
    lines.append("--- CONTEXTE EXTRAIT ---")
    lines.append(extracted or "[vide]")
    lines.append("--- FIN CONTEXTE ---")
    lines.append(f"QUESTION : {question.strip()}")
    return "\n".join(lines)


async def ask_llama(question: str, context: dict[str, Any]) -> str:
    """Envoie question + contexte texte à Ollama (modèle text-only)."""
    if not (question or "").strip():
        raise ValueError("Question vide.")

    extracted = (context.get("extracted_text") or "").strip()
    if not extracted:
        return "Je ne trouve pas cette information dans le document — le fichier ne contient pas de texte exploitable."

    model = settings.ollama_model
    base = settings.ollama_base_url.rstrip("/")
    user_msg = _build_user_message(question, context)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": DOCUMENT_QA_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        "stream": False,
        "think": False,
        "options": {"temperature": 0.2},
    }

    timeout = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(f"{base}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()

    reply = (data.get("message") or {}).get("content") or ""
    reply = reply.strip()
    if not reply:
        return "Je ne trouve pas cette information dans le document."

    logger.info("ask_llama model=%s question_len=%s context_len=%s reply_len=%s",
                model, len(question), len(extracted), len(reply))
    return reply


def format_assistant_preamble(context: dict[str, Any]) -> str:
    """Messages clairs pour l'utilisateur avant la réponse LLM."""
    parts: list[str] = []
    warnings = context.get("warnings") or []
    file_type = (context.get("file_type") or "").lower()

    if file_type == ".pdf" and any("PDF" in w for w in warnings):
        parts.append("J'ai extrait le texte du PDF.")
    if any("scanné" in w.lower() or "OCR" in w for w in warnings):
        parts.append("Ce PDF semble scanné, j'ai utilisé OCR.")
    meta = context.get("metadata") or {}
    sheets = meta.get("sheets")
    if sheets:
        parts.append(f"Ce fichier Excel contient les feuilles suivantes : {', '.join(sheets)}.")
    if file_type in {".png", ".jpg", ".jpeg", ".webp"}:
        if any("vision" in w.lower() for w in warnings):
            parts.append(
                "Cette image ne peut pas être analysée visuellement avec llama3.2:3b, "
                "mais j'ai extrait le texte visible."
            )

    if context.get("truncated"):
        parts.append("Le document est long — seules les sections les plus pertinentes ont été envoyées au modèle.")

    return "\n".join(parts)
