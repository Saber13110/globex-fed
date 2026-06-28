from __future__ import annotations

import re
from typing import Any

from jarvis.kernel.settings import settings
from jarvis.providers.documents.file_ingestion import ingest_file
from jarvis.providers.documents.types import FileContext

_WORD_RE = re.compile(r"[a-zA-Zàâäéèêëïîôùûüç0-9]{3,}", re.I)


def build_context_from_file(
    data: bytes,
    *,
    filename: str,
    mime_type: str | None = None,
    question: str = "",
) -> FileContext:
    """Extrait et structure le contenu fichier pour le LLM text-only."""
    return ingest_file(data, filename=filename, mime_type=mime_type, question=question)


def select_context_for_question(
    question: str,
    file_context: FileContext,
    *,
    max_chars: int | None = None,
) -> str:
    """Découpe le texte et ne garde que les passages pertinents pour la question."""
    limit = max_chars or settings.document_max_context_chars
    text = (file_context.extracted_text or "").strip()
    if not text:
        return ""

    if len(text) <= limit:
        return text

    chunks = _chunk_text(text, settings.document_chunk_size)
    if not chunks:
        return text[:limit]

    keywords = _keywords_from_question(question)
    if not keywords:
        return text[:limit]

    scored: list[tuple[int, int, str]] = []
    for idx, chunk in enumerate(chunks):
        score = sum(1 for kw in keywords if kw in chunk.lower())
        scored.append((score, idx, chunk))

    scored.sort(key=lambda x: (-x[0], x[1]))
    selected: list[str] = []
    total = 0
    for score, _idx, chunk in scored:
        if score <= 0 and selected:
            continue
        if total + len(chunk) > limit:
            remaining = limit - total
            if remaining > 200:
                selected.append(chunk[:remaining])
            break
        selected.append(chunk)
        total += len(chunk) + 2

    if not selected:
        return text[:limit]

    return "\n\n".join(selected)


def merge_context_payload(
    file_context: FileContext,
    question: str,
) -> dict[str, Any]:
    """Prépare le dict context pour ask_llama."""
    relevant = select_context_for_question(question, file_context)
    return {
        "file_name": file_context.file_name,
        "file_type": file_context.file_type,
        "extracted_text": relevant,
        "metadata": file_context.metadata,
        "warnings": file_context.warnings,
        "truncated": len(relevant) < len(file_context.extracted_text or ""),
    }


def _chunk_text(text: str, chunk_size: int) -> list[str]:
    if chunk_size <= 0:
        return [text]
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            break_at = text.rfind("\n", start, end)
            if break_at > start + chunk_size // 2:
                end = break_at
        parts.append(text[start:end].strip())
        start = end
    return [p for p in parts if p]


def _keywords_from_question(question: str) -> list[str]:
    words = _WORD_RE.findall(question or "")
    stop = {
        "the", "and", "for", "que", "qui", "dans", "avec", "pour", "les", "des", "une", "est",
        "sur", "par", "pas", "plus", "tout", "cette", "cet", "comment", "quoi", "quel", "quelle",
    }
    return [w.lower() for w in words if w.lower() not in stop][:20]
