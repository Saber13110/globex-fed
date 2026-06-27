"""Recherche dans la base de connaissances — hybride vectoriel + mots-clés (Phase 3)."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.gpt_definition import GptDefinition, KnowledgeChunk, KnowledgeCollection, KnowledgeDocument
from app.services.gpt.embedding_service import EmbeddingError, embed_query
from app.services.gpt.rag_profiler import RagProfile, timed_step
from app.services.gpt.vector_store import search_vectors
from app.services.llm.providers import normalize_lang_code

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeHit:
    chunk_id: int
    title: str
    content: str
    source_ref: str
    score: float
    retrieval: str = "keyword"  # keyword | vector | hybrid


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Zàâäéèêëïîôùûüç0-9]{3,}", (text or "").lower())
    return set(words)


def _score_chunk(query_tokens: set[str], chunk: KnowledgeChunk) -> float:
    if not query_tokens:
        return 0.0
    hay = f"{chunk.title} {chunk.keywords} {chunk.content}".lower()
    hay_tokens = _tokenize(hay)
    keyword_tokens = _tokenize(chunk.keywords.replace(",", " "))
    overlap = len(query_tokens & hay_tokens)
    keyword_bonus = len(query_tokens & keyword_tokens) * 2.0
    return overlap + keyword_bonus


def _gpt_collection_ids(gpt: GptDefinition) -> list[int]:
    try:
        raw = json.loads(gpt.knowledge_collection_ids_json or "[]")
        if isinstance(raw, list) and raw:
            return [int(x) for x in raw]
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return []


def _fetch_chunks_by_ids(db: Session, chunk_ids: list[int]) -> dict[int, KnowledgeChunk]:
    if not chunk_ids:
        return {}
    rows = list(db.scalars(select(KnowledgeChunk).where(KnowledgeChunk.id.in_(chunk_ids))).all())
    return {r.id: r for r in rows}


def list_knowledge_inventory(db: Session, *, gpt: GptDefinition) -> list[dict[str, str]]:
    """Liste les documents indexés pour un GPT (réponse RAG rapide)."""
    collection_ids = _gpt_collection_ids(gpt)
    stmt = (
        select(KnowledgeDocument, KnowledgeCollection)
        .join(KnowledgeCollection, KnowledgeDocument.collection_id == KnowledgeCollection.id)
        .where(KnowledgeDocument.status == "indexed")
        .order_by(KnowledgeDocument.created_at.desc())
        .limit(25)
    )
    if collection_ids:
        stmt = stmt.where(KnowledgeDocument.collection_id.in_(collection_ids))
    else:
        stmt = stmt.where(KnowledgeCollection.gpt_id == gpt.id)

    rows = db.execute(stmt).all()
    out: list[dict[str, str]] = []
    for doc, coll in rows:
        out.append(
            {
                "filename": doc.original_filename or doc.title or f"doc-{doc.id}",
                "collection": coll.name or f"collection-{coll.id}",
                "indexed_at": doc.created_at.isoformat() if doc.created_at else "",
                "language": doc.language or "",
            }
        )
    return out


def summarize_latest_document(db: Session, *, gpt: GptDefinition, max_chars: int = 1200) -> str:
    """Résumé textuel du dernier document indexé."""
    collection_ids = _gpt_collection_ids(gpt)
    stmt = (
        select(KnowledgeDocument)
        .join(KnowledgeCollection)
        .where(KnowledgeDocument.status == "indexed")
        .order_by(KnowledgeDocument.created_at.desc())
        .limit(1)
    )
    if collection_ids:
        stmt = stmt.where(KnowledgeDocument.collection_id.in_(collection_ids))
    else:
        stmt = stmt.where(KnowledgeCollection.gpt_id == gpt.id)
    doc = db.scalar(stmt)
    if doc is None:
        return ""

    chunks = list(
        db.scalars(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == doc.id)
            .order_by(KnowledgeChunk.chunk_index.asc())
            .limit(4)
        ).all()
    )
    if not chunks:
        return f"Document « {doc.original_filename or doc.title} » indexé sans extrait textuel."

    excerpt = "\n".join((c.content or "").strip() for c in chunks if (c.content or "").strip())
    if len(excerpt) > max_chars:
        excerpt = excerpt[:max_chars] + "…"
    return (
        f"Dernier document : « {doc.original_filename or doc.title} » "
        f"(indexé le {doc.created_at.strftime('%Y-%m-%d %H:%M') if doc.created_at else '—'}).\n"
        f"Extrait :\n{excerpt}"
    )


def _keyword_retrieve(
    db: Session,
    *,
    gpt: GptDefinition,
    query: str,
    lang: str,
    top_k: int,
    min_score: float,
) -> list[KnowledgeHit]:
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    collection_ids = _gpt_collection_ids(gpt)
    stmt = select(KnowledgeChunk).join(KnowledgeCollection)
    if collection_ids:
        stmt = stmt.where(KnowledgeChunk.collection_id.in_(collection_ids))
    else:
        stmt = stmt.where(KnowledgeCollection.gpt_id == gpt.id)

    stmt = stmt.where(KnowledgeChunk.language == lang)
    chunks = list(db.scalars(stmt).all())

    if not chunks and lang != "fr":
        stmt_fr = select(KnowledgeChunk).join(KnowledgeCollection)
        if collection_ids:
            stmt_fr = stmt_fr.where(KnowledgeChunk.collection_id.in_(collection_ids))
        else:
            stmt_fr = stmt_fr.where(KnowledgeCollection.gpt_id == gpt.id)
        chunks = list(db.scalars(stmt_fr.where(KnowledgeChunk.language == "fr")).all())

    scored: list[KnowledgeHit] = []
    for chunk in chunks:
        score = _score_chunk(query_tokens, chunk)
        if score >= min_score:
            scored.append(
                KnowledgeHit(
                    chunk_id=chunk.id,
                    title=chunk.title,
                    content=chunk.content,
                    source_ref=chunk.source_ref,
                    score=score,
                    retrieval="keyword",
                )
            )
    scored.sort(key=lambda h: h.score, reverse=True)
    return scored[:top_k]


def _vector_retrieve(
    db: Session,
    *,
    gpt: GptDefinition,
    query: str,
    language: str,
    top_k: int,
    min_score: float,
    profile: RagProfile | None = None,
) -> list[KnowledgeHit]:
    settings = get_settings()
    if not settings.gpt_rag_vector_enabled or not (settings.gemini_api_key or "").strip():
        return []

    try:
        with timed_step(profile, "embed_query"):
            query_vec = embed_query(query)
    except EmbeddingError as exc:
        logger.warning("Embedding requête RAG échoué : %s", exc)
        return []

    collection_ids = _gpt_collection_ids(gpt) or None
    with timed_step(profile, "vector_search"):
        pairs, mode = search_vectors(
            db,
            query_vector=query_vec,
            collection_ids=collection_ids,
            gpt_id=gpt.id if not collection_ids else None,
            language=language,
            top_k=top_k,
        )
    if profile:
        profile.add("vector_search_mode", detail=mode)

    if not pairs and language != "fr":
        pairs, mode = search_vectors(
            db,
            query_vector=query_vec,
            collection_ids=collection_ids,
            gpt_id=gpt.id if not collection_ids else None,
            language="fr",
            top_k=top_k,
        )
        if profile:
            profile.add("vector_search_mode_fr", detail=mode)

    by_id = _fetch_chunks_by_ids(db, [cid for cid, _ in pairs])
    hits: list[KnowledgeHit] = []
    for chunk_id, score in pairs:
        if score < min_score:
            continue
        chunk = by_id.get(chunk_id)
        if chunk is None:
            continue
        hits.append(
            KnowledgeHit(
                chunk_id=chunk.id,
                title=chunk.title,
                content=chunk.content,
                source_ref=chunk.source_ref,
                score=score,
                retrieval=mode if mode == "pgvector" else "vector",
            )
        )
    return hits


def _merge_hits(
    vector_hits: list[KnowledgeHit],
    keyword_hits: list[KnowledgeHit],
    *,
    top_k: int,
) -> list[KnowledgeHit]:
    merged: dict[int, KnowledgeHit] = {}
    for hit in vector_hits:
        merged[hit.chunk_id] = hit
    for hit in keyword_hits:
        existing = merged.get(hit.chunk_id)
        if existing is None:
            merged[hit.chunk_id] = hit
        else:
            combined = max(existing.score, hit.score * 0.85)
            merged[hit.chunk_id] = KnowledgeHit(
                chunk_id=existing.chunk_id,
                title=existing.title,
                content=existing.content,
                source_ref=existing.source_ref,
                score=combined,
                retrieval="hybrid",
            )
    ordered = sorted(merged.values(), key=lambda h: h.score, reverse=True)
    return ordered[:top_k]


def load_attached_document_text(
    db: Session,
    *,
    gpt: GptDefinition,
    filename: str,
    max_chars: int = 14_000,
) -> str:
    """Charge le texte intégral du dernier document uploadé correspondant au nom de fichier."""
    name = (filename or "").strip()
    if not name:
        return ""

    stmt = (
        select(KnowledgeDocument)
        .join(KnowledgeCollection)
        .where(
            KnowledgeCollection.gpt_id == gpt.id,
            KnowledgeDocument.status == "indexed",
            KnowledgeDocument.original_filename == name,
        )
        .order_by(KnowledgeDocument.created_at.desc())
        .limit(1)
    )
    doc = db.scalar(stmt)
    if doc is None:
        doc = db.scalar(
            select(KnowledgeDocument)
            .join(KnowledgeCollection)
            .where(
                KnowledgeCollection.gpt_id == gpt.id,
                KnowledgeDocument.status == "indexed",
                KnowledgeDocument.original_filename.ilike(f"%{name}%"),
            )
            .order_by(KnowledgeDocument.created_at.desc())
            .limit(1)
        )
    if doc is None:
        return ""

    chunks = list(
        db.scalars(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == doc.id)
            .order_by(KnowledgeChunk.chunk_index.asc())
        ).all()
    )
    if not chunks:
        return ""

    text = "\n\n".join((c.content or "").strip() for c in chunks if (c.content or "").strip())
    if len(text) > max_chars:
        return text[:max_chars] + "\n… [contenu tronqué]"
    return text


def extract_fedex_tracking_numbers(text: str, *, limit: int = 15) -> list[str]:
    """Extrait les numéros de suivi FedEx plausibles (12, 15, 20, 22 chiffres)."""
    if not text:
        return []
    allowed_lengths = {12, 15, 20, 22}
    seen: set[str] = set()
    out: list[str] = []
    for match in re.finditer(r"\b(\d{12,22})\b", text):
        candidate = match.group(1)
        if len(candidate) not in allowed_lengths or candidate in seen:
            continue
        seen.add(candidate)
        out.append(candidate)
        if len(out) >= limit:
            break
    return out


def build_attachment_context(
    db: Session,
    *,
    gpt: GptDefinition,
    filename: str | None,
    user_message: str,
) -> tuple[str, str]:
    """
    Retourne (contenu_fichier, consigne_serveur) pour un document admin joint.
    Le serveur a déjà extrait le texte — Gemini n'a pas à « ouvrir » le fichier lui-même.
    """
    if not filename:
        return "", ""

    file_text = load_attached_document_text(db, gpt=gpt, filename=filename)
    if not file_text:
        return "", (
            f"Le fichier « {filename} » est référencé mais son texte n'a pas été retrouvé en base. "
            f"Demandez à l'admin de le renvoyer via le trombone."
        )

    tracking = extract_fedex_tracking_numbers(file_text)
    wants_tracking = bool(re.search(r"\b(suivi|tracking|colis|track|expédition|expedition)\b", user_message, re.I))

    instruction = (
        f"Le serveur Globex a DÉJÀ LU et extrait le fichier « {filename} ». "
        f"Son contenu intégral est dans ATTACHED_FILE ci-dessous — ne dites JAMAIS que vous ne pouvez pas lire un fichier.\n"
        f"Utilisez ATTACHED_FILE comme source principale pour répondre."
    )
    if tracking:
        instruction += f"\nNuméros de suivi détectés dans le fichier : {', '.join(tracking)}."
    if wants_tracking and tracking:
        instruction += (
            "\nL'admin demande un suivi : appelez fedex_track_package pour CHAQUE numéro ci-dessus, "
            "puis présentez un tableau récapitulatif (numéro, statut, lieu, ETA)."
        )
    elif wants_tracking:
        instruction += (
            "\nL'admin demande un suivi : cherchez les numéros dans ATTACHED_FILE puis appelez fedex_track_package."
        )

    return file_text, instruction


def retrieve_knowledge(
    db: Session,
    *,
    gpt: GptDefinition,
    query: str,
    language: str | None = None,
    top_k: int = 4,
    min_score: float = 1.0,
    skip_vector: bool = False,
    profile: RagProfile | None = None,
) -> list[KnowledgeHit]:
    """Recherche hybride : embeddings PGVector + recouvrement mots-clés."""
    lang = normalize_lang_code(language or gpt.default_language)
    settings = get_settings()

    with timed_step(profile, "keyword_retrieve_start"):
        keyword_hits = _keyword_retrieve(
            db,
            gpt=gpt,
            query=query,
            lang=lang,
            top_k=top_k,
            min_score=min_score,
        )
    if profile:
        profile.add("keyword_retrieve_done", detail=f"hits={len(keyword_hits)}")

    vector_hits: list[KnowledgeHit] = []
    if not skip_vector:
        with timed_step(profile, "vector_retrieve_start"):
            vector_min = settings.gpt_rag_hybrid_min_score if settings.gpt_rag_vector_enabled else 1.0
            vector_top = max(top_k, settings.gpt_rag_vector_top_k)
            vector_hits = _vector_retrieve(
                db,
                gpt=gpt,
                query=query,
                language=lang,
                top_k=vector_top,
                min_score=vector_min,
                profile=profile,
            )
        if profile:
            profile.add("vector_retrieve_done", detail=f"hits={len(vector_hits)}")
    elif profile:
        profile.add("vector_retrieve_skipped", detail="skip_vector=true")

    if vector_hits and keyword_hits:
        merged = _merge_hits(vector_hits, keyword_hits, top_k=top_k)
        if profile:
            profile.add("merge_hits", detail=f"total={len(merged)}")
        return merged
    if vector_hits:
        return vector_hits[:top_k]
    return keyword_hits


def format_knowledge_block(hits: list[KnowledgeHit], *, intent: str | None = None) -> str:
    from app.services.gpt.intent_classifier import INTENT_KNOWLEDGE

    if not hits:
        if intent == INTENT_KNOWLEDGE:
            return (
                "Aucun extrait pertinent en base de connaissances. "
                "Dites clairement que l'information n'est pas disponible en base — "
                "ne fabriquez pas de contenu."
            )
        return (
            "Aucun extrait pertinent en base. Répondez avec prudence ; orientez vers fedex.com "
            "ou le support FedEx (1-800-463-3339) si nécessaire. Ne fabriquez pas de procédure."
        )
    parts: list[str] = [
        "Référence interne (à synthétiser en prose naturelle — ne pas recopier les titres « Extrait ») :"
    ]
    for hit in hits:
        src = f" ({hit.source_ref})" if hit.source_ref else ""
        content = hit.content
        if intent == INTENT_KNOWLEDGE and len(content) > 900:
            content = content[:900] + "…"
        parts.append(f"• {hit.title}{src}\n{content}")
    return "\n\n".join(parts)
