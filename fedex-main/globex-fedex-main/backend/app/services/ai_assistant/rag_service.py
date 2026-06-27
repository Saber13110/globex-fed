"""Service RAG entreprise — wrapper base connaissances GPT."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.gpt_definition import GptDefinition
from app.services.gpt.knowledge_service import (
    format_knowledge_block,
    retrieve_knowledge,
)


def search_knowledge(
    db: Session,
    *,
    gpt: GptDefinition,
    query: str,
    language: str = "fr",
    top_k: int = 5,
) -> dict[str, Any]:
    hits = retrieve_knowledge(
        db, gpt=gpt, query=query, language=language, top_k=top_k, min_score=0.35,
    )
    sources = [
        {
            "chunk_id": h.chunk_id,
            "title": h.title,
            "score": round(h.score, 3),
            "snippet": (h.content or "")[:300],
            "retrieval": h.retrieval,
        }
        for h in hits
    ]
    return {
        "hits": hits,
        "sources": sources,
        "block": format_knowledge_block(hits),
        "count": len(hits),
    }
