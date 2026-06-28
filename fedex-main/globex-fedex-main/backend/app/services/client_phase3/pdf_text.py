"""PDF texte libre — le LLM rédige le corps, fpdf met en page."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fpdf.errors import FPDFException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.chat_message import ChatMessage, MessageSender
from app.models.chat_session import ChatSession
from app.models.user import User
from app.services.ai_assistant.export_dataset_cache import store_client_pdf_blob
from app.services.chat_session_context import build_conversation_history_for_llm
from app.services.client_phase3.pdf_body_composer import strip_markdown_for_pdf
from app.services.copilot_export_service import build_export_download_spec
from app.services.llm.providers import LlmProviderError, _extract_ollama_text, normalize_lang_code
from app.services.llm.prompts import language_lock_instruction
from app.services.message_attachment import unpack_message_text
from app.services.simple_text_pdf_service import generate_text_pdf

logger = logging.getLogger(__name__)

_PDF_DRAFT_SYSTEM = (
    "Tu rédiges le CONTENU d'un document PDF pour un client FedEx Globex.\n"
    "Règles strictes :\n"
    "- Rédige UNIQUEMENT le texte du document (titres et paragraphes).\n"
    "- INTERDIT : « je vais préparer », « patientez », « cliquez ici », boutons, liens.\n"
    "- Pour un résumé de conversation : synthèse fidèle de ce qui a été dit.\n"
    "- Pour les faits colis : utilise UNIQUEMENT les informations présentes dans l'historique ; "
    "n'invente pas de statut, date ou lieu.\n"
    "- Longueur : 150 à 600 mots selon la demande."
)

_PDF_READY_NOTE = (
    "\n\n---\n"
    "Votre document PDF est prêt — utilisez le lien de téléchargement ci-dessous."
)


def last_bot_message_text(db: Session, session_id: int) -> str | None:
    for msg in db.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(12)
    ).all():
        if msg.sender != "bot":
            continue
        text, _, _ = unpack_message_text(msg.message_text or "")
        text = (text or "").strip()
        if text:
            return text
    return None


def recent_bot_message_texts(db: Session, session_id: int, *, limit: int = 5) -> list[str]:
    texts: list[str] = []
    for msg in db.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit * 3)
    ).all():
        if msg.sender != "bot":
            continue
        text, _, _ = unpack_message_text(msg.message_text or "")
        text = (text or "").strip()
        if text:
            texts.append(text)
        if len(texts) >= limit:
            break
    return texts


_TRANSCRIPT_TITLE = "Conversation FedEx Globex"
_TRANSCRIPT_SEPARATOR = "=" * 32
_MAX_TRANSCRIPT_MESSAGES = 50
_MAX_TRANSCRIPT_CHARS_PER_MSG = 4000


def build_session_transcript_text(
    db: Session,
    session_id: int,
    *,
    exclude_message_id: int | None = None,
    limit: int = _MAX_TRANSCRIPT_MESSAGES,
) -> str:
    """Transcript fidèle des messages de session (sans Ollama)."""
    cap = max(1, min(limit, _MAX_TRANSCRIPT_MESSAGES))
    rows = list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(cap + (1 if exclude_message_id else 0))
        ).all()
    )
    lines: list[str] = [_TRANSCRIPT_TITLE, _TRANSCRIPT_SEPARATOR, ""]
    count = 0
    for row in reversed(rows):
        if exclude_message_id and row.id == exclude_message_id:
            continue
        text, _, _ = unpack_message_text(row.message_text or "")
        text = (text or "").strip()
        if not text:
            continue
        if len(text) > _MAX_TRANSCRIPT_CHARS_PER_MSG:
            text = text[:_MAX_TRANSCRIPT_CHARS_PER_MSG] + "…"
        role = "Utilisateur" if row.sender == MessageSender.user.value else "Assistant"
        lines.append(f"{role}: {text}")
        lines.append("")
        count += 1
        if count >= cap:
            break
    if count == 0:
        return ""
    return "\n".join(lines).strip()


def draft_pdf_content(
    user_request: str,
    *,
    conversation_history: str | None,
    ui_language: str | None,
) -> str:
    settings = get_settings()
    if not settings.llm_enabled:
        raise LlmProviderError("LLM désactivé (LLM_ENABLED=false).")

    lang = normalize_lang_code(ui_language)
    system = f"{_PDF_DRAFT_SYSTEM}\n{language_lock_instruction(lang)}"
    hist_block = ""
    if conversation_history and conversation_history.strip():
        hist = conversation_history.strip()[:1200]
        hist_block = f"\n\n===HISTORIQUE===\n{hist}\n"
    prompt = (
        f"===SYSTEM===\n{system}\n"
        f"{hist_block}\n"
        f"===DEMANDE===\n{(user_request or '').strip()}\n\n"
        "Rédige le contenu du PDF maintenant :"
    )

    base = settings.ollama_base_url.rstrip("/")
    body = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.35, "num_predict": 256, "num_ctx": 1536},
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


def build_text_pdf_artifact(
    user_id: int,
    body: str,
    *,
    title: str,
    session_id: int,
) -> tuple[dict[str, Any], bytes, str]:
    """Génère le blob PDF et retourne (export_download, pdf_bytes, filename)."""
    cleaned_body = strip_markdown_for_pdf(body)
    try:
        pdf_bytes, filename = generate_text_pdf(cleaned_body, title=title)
    except FPDFException as exc:
        raise ValueError(
            "Impossible de générer le fichier PDF. Réessayez ou reformulez votre demande."
        ) from exc
    token = store_client_pdf_blob(
        user_id=user_id,
        pdf_bytes=pdf_bytes,
        filename=filename,
        meta={"text_preview": cleaned_body[:200]},
    )
    spec = build_export_download_spec(
        preset="text_pdf",
        filename=filename,
        fmt="pdf",
        export_token=token,
        session_id=session_id,
    )
    return spec, pdf_bytes, filename


def build_text_pdf_download(
    user_id: int,
    body: str,
    *,
    title: str,
    session_id: int,
) -> dict[str, Any]:
    """Génère le blob PDF et retourne la spec export_download."""
    spec, _, _ = build_text_pdf_artifact(
        user_id,
        body,
        title=title,
        session_id=session_id,
    )
    return spec


def append_pdf_ready_note(reply: str) -> str:
    text = (reply or "").strip()
    if not text:
        return _PDF_READY_NOTE.strip()
    if "lien de téléchargement" in text.lower():
        return text
    return f"{text}{_PDF_READY_NOTE}"


def run_text_pdf_export(
    db: Session,
    user: User,
    session: ChatSession,
    message: str,
    *,
    user_msg_id: int,
    ui_language: str | None,
    use_last_bot_reply: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Génère un PDF texte et retourne (reply_courte, export_download)."""
    if use_last_bot_reply:
        body = last_bot_message_text(db, session.id)
        if not body:
            return (
                "Je n'ai pas trouvé de réponse précédente à mettre en PDF. "
                "Posez une question puis demandez le PDF de ma réponse.",
                {},
            )
        title = "Réponse assistant FedEx"
    else:
        history = build_conversation_history_for_llm(
            db,
            session_id=session.id,
            exclude_message_id=user_msg_id,
            limit=8,
        )
        try:
            body = draft_pdf_content(
                message,
                conversation_history=history,
                ui_language=ui_language,
            )
        except LlmProviderError:
            logger.warning("Phase 3 PDF text draft failed", exc_info=True)
            return (
                "Désolé, je n'ai pas pu rédiger le contenu du PDF pour le moment. Réessayez plus tard.",
                {},
            )
        title = "Résumé FedEx Globex"

    try:
        export_download = build_text_pdf_download(
            user.id,
            body,
            title=title,
            session_id=session.id,
        )
    except ValueError as exc:
        return str(exc), {}

    reply = append_pdf_ready_note(body)
    return reply, export_download
