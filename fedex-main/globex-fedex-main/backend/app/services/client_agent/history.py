# =============================================================================
# LEGACY DESACTIVE — refonte client_agent v2 (Phase 0)
# Ne pas réactiver sans retirer le bloc ACTIVE ci-dessous.
# =============================================================================
# """Historique session pour Ollama /api/chat."""
#
# from __future__ import annotations
#
# from sqlalchemy import select
# from sqlalchemy.orm import Session
#
# from app.models.chat_message import ChatMessage, MessageSender
# from app.services.message_attachment import unpack_message_text
#
# _MAX_CONTENT_CHARS = 2000
# _SKIP_SOURCES = frozenset({"security"})
#
#
# def load_ollama_history(
#     db: Session,
#     session_id: int,
#     *,
#     limit: int = 20,
#     exclude_message_id: int | None = None,
# ) -> list[dict[str, str]]:
#     """
#     Charge les messages récents de la session au format Ollama /api/chat.
#
#     Le message utilisateur courant est enregistré avant run_turn : passer
#     exclude_message_id pour éviter de le dupliquer dans l'historique.
#     """
#     fetch_limit = limit + (5 if exclude_message_id else 0)
#     rows = list(
#         db.scalars(
#             select(ChatMessage)
#             .where(ChatMessage.session_id == session_id)
#             .order_by(ChatMessage.created_at.desc())
#             .limit(fetch_limit)
#         ).all()
#     )
#
#     chronological = list(reversed(rows))
#     out: list[dict[str, str]] = []
#
#     for row in chronological:
#         if exclude_message_id is not None and row.id == exclude_message_id:
#             continue
#         if (row.source or "").strip().lower() in _SKIP_SOURCES:
#             continue
#
#         text, _, _ = unpack_message_text(row.message_text or "")
#         text = (text or "").strip()
#         if not text:
#             continue
#         if len(text) > _MAX_CONTENT_CHARS:
#             text = text[:_MAX_CONTENT_CHARS] + "…"
#
#         sender = (row.sender or "").strip().lower()
#         if sender == MessageSender.user.value:
#             role = "user"
#         elif sender == MessageSender.bot.value:
#             role = "assistant"
#         else:
#             continue
#
#         out.append({"role": role, "content": text})
#         if len(out) >= limit:
#             break
#
#     return out
# =============================================================================
# ACTIVE — Phase 0 stub
# =============================================================================
"""client_agent — stub Phase 0."""
