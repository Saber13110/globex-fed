"""Stockage et recherche vectorielle PGVector (fallback Python)."""

from __future__ import annotations

import json
import logging
import math
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_PGVECTOR_READY: bool | None = None
_PGVECTOR_CHECKED: bool = False

VectorSearchMode = Literal["pgvector", "python"]


def pgvector_extension_available(engine: Engine) -> bool:
    """True si l'extension « vector » est proposée par ce serveur PostgreSQL."""
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT 1 FROM pg_available_extensions "
                    "WHERE name = 'vector' LIMIT 1"
                )
            ).first()
            return row is not None
    except Exception:
        return False


def ensure_pgvector(engine: Engine) -> bool:
    """Active l'extension vector si disponible sur le serveur."""
    global _PGVECTOR_READY, _PGVECTOR_CHECKED
    if _PGVECTOR_READY is not None:
        return _PGVECTOR_READY

    settings = get_settings()
    if not settings.gpt_rag_pgvector_enabled:
        _PGVECTOR_READY = False
        if not _PGVECTOR_CHECKED:
            logger.info(
                "PGVector désactivé (GPT_RAG_PGVECTOR_ENABLED=false) — "
                "recherche vectorielle via embedding_json (Python)."
            )
            _PGVECTOR_CHECKED = True
        return False

    if not pgvector_extension_available(engine):
        _PGVECTOR_READY = False
        if not _PGVECTOR_CHECKED:
            logger.info(
                "Extension PostgreSQL « vector » non installée sur ce serveur — "
                "recherche vectorielle via embedding_json (Python). "
                "Pour activer PGVector : installez l'extension pgvector sur PostgreSQL "
                "ou utilisez une image Docker pgvector/pgvector."
            )
            _PGVECTOR_CHECKED = True
        return False

    try:
        dims = max(int(get_settings().gemini_embedding_dimensions or 768), 1)
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.execute(
                text(
                    f"ALTER TABLE knowledge_chunks "
                    f"ADD COLUMN IF NOT EXISTS embedding vector({dims})"
                )
            )
        _PGVECTOR_READY = True
        logger.info("PGVector activé pour knowledge_chunks.embedding")
    except Exception as exc:
        _PGVECTOR_READY = False
        logger.warning("PGVector activation échouée — fallback Python : %s", exc)
    _PGVECTOR_CHECKED = True
    return _PGVECTOR_READY


def store_chunk_embedding(db: Session, *, chunk_id: int, vector: list[float]) -> None:
    """Persiste embedding JSON + colonne vector si PGVector actif."""
    from app.core.database import engine
    from app.models.gpt_definition import KnowledgeChunk

    chunk = db.get(KnowledgeChunk, chunk_id)
    if chunk is None:
        return
    chunk.embedding_json = json.dumps(vector)
    db.flush()

    if ensure_pgvector(engine):
        literal = "[" + ",".join(f"{v:.8f}" for v in vector) + "]"
        db.execute(
            text("UPDATE knowledge_chunks SET embedding = CAST(:vec AS vector) WHERE id = :id"),
            {"vec": literal, "id": chunk_id},
        )


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def search_pgvector(
    db: Session,
    *,
    query_vector: list[float],
    collection_ids: list[int] | None,
    gpt_id: int | None,
    language: str,
    top_k: int,
) -> list[tuple[int, float]]:
    """Recherche par distance cosinus PGVector. Retourne [(chunk_id, score)]."""
    from app.core.database import engine

    if not ensure_pgvector(engine):
        return []

    literal = "[" + ",".join(f"{v:.8f}" for v in query_vector) + "]"
    filters = ["kc.language = :lang", "kc.embedding IS NOT NULL"]
    params: dict[str, Any] = {"lang": language, "qvec": literal, "top_k": top_k}

    if collection_ids:
        ids_sql = ",".join(str(int(x)) for x in collection_ids)
        filters.append(f"kc.collection_id IN ({ids_sql})")
    elif gpt_id is not None:
        filters.append("kc.collection_id IN (SELECT id FROM knowledge_collections WHERE gpt_id = :gpt_id)")
        params["gpt_id"] = gpt_id

    where_sql = " AND ".join(filters)
    sql = text(
        f"""
        SELECT kc.id,
               1 - (kc.embedding <=> CAST(:qvec AS vector)) AS score
        FROM knowledge_chunks kc
        WHERE {where_sql}
        ORDER BY kc.embedding <=> CAST(:qvec AS vector)
        LIMIT :top_k
        """
    )
    rows = db.execute(sql, params).fetchall()
    return [(int(r[0]), float(r[1])) for r in rows if r[1] is not None]


def search_python_fallback(
    db: Session,
    *,
    query_vector: list[float],
    collection_ids: list[int] | None,
    gpt_id: int | None,
    language: str,
    top_k: int,
) -> list[tuple[int, float]]:
    """Recherche cosinus en Python sur embedding_json."""
    from sqlalchemy import select

    from app.models.gpt_definition import KnowledgeChunk, KnowledgeCollection

    stmt = select(KnowledgeChunk).join(KnowledgeCollection)
    if collection_ids:
        stmt = stmt.where(KnowledgeChunk.collection_id.in_(collection_ids))
    elif gpt_id is not None:
        stmt = stmt.where(KnowledgeCollection.gpt_id == gpt_id)
    stmt = stmt.where(
        KnowledgeChunk.language == language,
        KnowledgeChunk.embedding_json.isnot(None),
        KnowledgeChunk.embedding_json != "",
    )
    chunks = list(db.scalars(stmt).all())
    scored: list[tuple[int, float]] = []
    for chunk in chunks:
        try:
            vec = json.loads(chunk.embedding_json or "[]")
            if not isinstance(vec, list):
                continue
            score = _cosine_similarity(query_vector, [float(v) for v in vec])
            if score > 0:
                scored.append((chunk.id, score))
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def search_vectors(
    db: Session,
    *,
    query_vector: list[float],
    collection_ids: list[int] | None,
    gpt_id: int | None,
    language: str,
    top_k: int,
) -> tuple[list[tuple[int, float]], VectorSearchMode]:
    """Recherche vectorielle : PGVector si disponible, sinon cosinus Python sur embedding_json."""
    pairs = search_pgvector(
        db,
        query_vector=query_vector,
        collection_ids=collection_ids,
        gpt_id=gpt_id,
        language=language,
        top_k=top_k,
    )
    if pairs:
        return pairs, "pgvector"
    pairs = search_python_fallback(
        db,
        query_vector=query_vector,
        collection_ids=collection_ids,
        gpt_id=gpt_id,
        language=language,
        top_k=top_k,
    )
    return pairs, "python"
