"""API métier admin — gestion base de connaissances GPT."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.gpt_definition import GptDefinition, KnowledgeChunk, KnowledgeCollection, KnowledgeDocument
from app.services.gpt.document_ingestion_service import (
    DocumentIngestError,
    ingest_uploaded_document,
    reindex_chunks_without_embeddings,
)
from app.services.gpt.orchestrator import load_gpt_by_slug


def list_gpt_knowledge_overview(db: Session) -> dict[str, Any]:
    gpts = list(db.scalars(select(GptDefinition).where(GptDefinition.is_active.is_(True))).all())
    items: list[dict[str, Any]] = []
    for gpt in gpts:
        coll_count = db.scalar(
            select(func.count()).select_from(KnowledgeCollection).where(KnowledgeCollection.gpt_id == gpt.id)
        ) or 0
        chunk_count = db.scalar(
            select(func.count())
            .select_from(KnowledgeChunk)
            .join(KnowledgeCollection)
            .where(KnowledgeCollection.gpt_id == gpt.id)
        ) or 0
        embedded = db.scalar(
            select(func.count())
            .select_from(KnowledgeChunk)
            .join(KnowledgeCollection)
            .where(
                KnowledgeCollection.gpt_id == gpt.id,
                KnowledgeChunk.embedding_json.isnot(None),
                KnowledgeChunk.embedding_json != "",
            )
        ) or 0
        doc_count = db.scalar(
            select(func.count())
            .select_from(KnowledgeDocument)
            .join(KnowledgeCollection)
            .where(KnowledgeCollection.gpt_id == gpt.id)
        ) or 0
        items.append(
            {
                "slug": gpt.slug,
                "name": gpt.name,
                "collections": coll_count,
                "chunks": chunk_count,
                "embedded_chunks": embedded,
                "documents": doc_count,
            }
        )
    return {"gpt_profiles": items}


def list_collections(db: Session, *, gpt_slug: str) -> list[dict[str, Any]]:
    gpt = load_gpt_by_slug(db, gpt_slug)
    if gpt is None:
        raise ValueError(f"GPT introuvable : {gpt_slug}")

    rows = list(
        db.scalars(select(KnowledgeCollection).where(KnowledgeCollection.gpt_id == gpt.id)).all()
    )
    out: list[dict[str, Any]] = []
    for coll in rows:
        chunk_count = db.scalar(
            select(func.count()).select_from(KnowledgeChunk).where(KnowledgeChunk.collection_id == coll.id)
        ) or 0
        doc_count = db.scalar(
            select(func.count()).select_from(KnowledgeDocument).where(KnowledgeDocument.collection_id == coll.id)
        ) or 0
        out.append(
            {
                "id": coll.id,
                "slug": coll.slug,
                "title": coll.title,
                "language": coll.language,
                "source_type": coll.source_type,
                "chunk_count": chunk_count,
                "document_count": doc_count,
            }
        )
    return out


def list_documents(db: Session, *, gpt_slug: str) -> list[dict[str, Any]]:
    gpt = load_gpt_by_slug(db, gpt_slug)
    if gpt is None:
        raise ValueError(f"GPT introuvable : {gpt_slug}")

    rows = list(
        db.scalars(
            select(KnowledgeDocument)
            .join(KnowledgeCollection)
            .where(KnowledgeCollection.gpt_id == gpt.id)
            .order_by(KnowledgeDocument.created_at.desc())
        ).all()
    )
    return [
        {
            "id": d.id,
            "collection_id": d.collection_id,
            "original_filename": d.original_filename,
            "file_size_bytes": d.file_size_bytes,
            "status": d.status,
            "chunk_count": d.chunk_count,
            "error_message": d.error_message or None,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in rows
    ]


def upload_document(
    db: Session,
    *,
    gpt_slug: str,
    file_bytes: bytes,
    filename: str,
    language: str,
    uploaded_by_user_id: int,
) -> dict[str, Any]:
    gpt = load_gpt_by_slug(db, gpt_slug)
    if gpt is None:
        raise ValueError(f"GPT introuvable : {gpt_slug}")

    doc = ingest_uploaded_document(
        db,
        gpt=gpt,
        file_bytes=file_bytes,
        filename=filename,
        language=language,
        uploaded_by_user_id=uploaded_by_user_id,
    )
    return {
        "document_id": doc.id,
        "filename": doc.original_filename,
        "status": doc.status,
        "chunk_count": doc.chunk_count,
    }


def delete_document(db: Session, *, document_id: int) -> bool:
    doc = db.get(KnowledgeDocument, document_id)
    if doc is None:
        return False
    db.delete(doc)
    db.commit()
    return True


def run_reindex(db: Session, *, gpt_slug: str | None = None) -> dict[str, int]:
    gpt_id = None
    if gpt_slug:
        gpt = load_gpt_by_slug(db, gpt_slug)
        if gpt is None:
            raise ValueError(f"GPT introuvable : {gpt_slug}")
        gpt_id = gpt.id
    count = reindex_chunks_without_embeddings(db, gpt_id=gpt_id, limit=500)
    return {"reindexed": count}
