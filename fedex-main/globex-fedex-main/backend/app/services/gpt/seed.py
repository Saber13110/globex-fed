"""Initialisation des GPT et ingestion de la base de connaissances FedEx."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.gpt_definition import GptDefinition, KnowledgeChunk, KnowledgeCollection
from app.services.gpt.prompts import ADMIN_GPT_SYSTEM_PROMPT
from app.services.llm.prompts import FEDEX_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

_CONTENT_DIR = Path(__file__).resolve().parent.parent.parent / "content"

_KNOWLEDGE_FILES = {
    "fr": "fedex_knowledge_fr.json",
    "en": "fedex_knowledge_en.json",
}

_CLIENT_TOOLS = [
    "fedex_track_package",
    "find_fedex_location",
    "client_watch_shipment",
    "client_open_support_ticket",
    "client_export_tracking_excel",
    "client_export_tracking_pdf",
    "client_generate_text_pdf",
]

_ADMIN_TOOLS = [
    "get_platform_stats",
    "analyze_tracking",
    "analyze_tickets",
    "analyze_users",
    "analyze_logs",
    "analyze_notifications",
    "analyze_conversations",
    "export_activity_logs_pdf",
    "export_activity_logs_excel",
    "fedex_track_package",
    "find_fedex_location",
    "suspend_user",
    "reactivate_user",
]


def _load_knowledge_file(lang: str) -> list[dict]:
    path = _CONTENT_DIR / _KNOWLEDGE_FILES.get(lang, _KNOWLEDGE_FILES["fr"])
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [row for row in data if isinstance(row, dict)]


def _upsert_gpt(
    db: Session,
    *,
    slug: str,
    name: str,
    description: str,
    system_prompt: str,
    welcome_message: str,
    default_language: str,
    allowed_roles: str,
    tool_ids: list[str],
    max_output_tokens: int = 1024,
) -> GptDefinition:
    row = db.scalar(select(GptDefinition).where(GptDefinition.slug == slug))
    tool_json = json.dumps(tool_ids, ensure_ascii=False)
    if row is None:
        row = GptDefinition(
            slug=slug,
            name=name,
            description=description,
            system_prompt=system_prompt,
            welcome_message=welcome_message,
            default_language=default_language,
            allowed_roles=allowed_roles,
            tool_ids_json=tool_json,
            knowledge_collection_ids_json="[]",
            max_output_tokens=max_output_tokens,
        )
        db.add(row)
        db.flush()
    else:
        row.name = name
        row.description = description
        row.system_prompt = system_prompt
        row.welcome_message = welcome_message
        row.allowed_roles = allowed_roles
        row.tool_ids_json = tool_json
        row.max_output_tokens = max_output_tokens
        row.is_active = True
    return row


def _upsert_collection(
    db: Session,
    *,
    gpt: GptDefinition,
    slug: str,
    title: str,
    language: str,
) -> KnowledgeCollection:
    row = db.scalar(
        select(KnowledgeCollection).where(
            KnowledgeCollection.gpt_id == gpt.id,
            KnowledgeCollection.slug == slug,
            KnowledgeCollection.language == language,
        )
    )
    if row is None:
        row = KnowledgeCollection(
            gpt_id=gpt.id,
            slug=slug,
            title=title,
            language=language,
            source_type="json",
            description=f"Base FedEx {language}",
        )
        db.add(row)
        db.flush()
    return row


def _ingest_chunks(db: Session, collection: KnowledgeCollection, rows: list[dict]) -> int:
    existing = {
        c.chunk_key
        for c in db.scalars(
            select(KnowledgeChunk).where(KnowledgeChunk.collection_id == collection.id)
        ).all()
    }
    added = 0
    for row in rows:
        key = str(row.get("key") or "").strip()
        if not key:
            continue
        if key in existing:
            chunk = db.scalar(
                select(KnowledgeChunk).where(
                    KnowledgeChunk.collection_id == collection.id,
                    KnowledgeChunk.chunk_key == key,
                )
            )
            if chunk:
                chunk.title = str(row.get("title") or key)
                chunk.content = str(row.get("content") or "")
                chunk.keywords = str(row.get("keywords") or "")
                chunk.source_ref = str(row.get("source") or "")
            continue
        db.add(
            KnowledgeChunk(
                collection_id=collection.id,
                chunk_key=key,
                title=str(row.get("title") or key),
                content=str(row.get("content") or ""),
                keywords=str(row.get("keywords") or ""),
                source_ref=str(row.get("source") or ""),
                language=collection.language,
            )
        )
        added += 1
    return added


def seed_gpt_platform(db: Session) -> None:
    """Crée ou met à jour les GPT Globex et ingère la KB FedEx."""
    client = _upsert_gpt(
        db,
        slug="fedex-client",
        name="Assistant FedEx Globex",
        description="Copilot client suivi colis, logistique et automatisation.",
        system_prompt=FEDEX_SYSTEM_PROMPT,
        welcome_message="Bonjour. Je suis votre assistant FedEx Globex — suivi de colis, logistique et automatisation. Que souhaitez-vous faire ?",
        default_language="fr",
        allowed_roles="client,employee",
        tool_ids=_CLIENT_TOOLS,
        max_output_tokens=1536,
    )
    admin = _upsert_gpt(
        db,
        slug="fedex-admin-ops",
        name="Copilot Super Admin Globex",
        description="Assistant opérationnel administrateur plateforme Globex FedEx.",
        system_prompt=ADMIN_GPT_SYSTEM_PROMPT,
        welcome_message="Bonjour. Copilot Super Admin Globex — opérations, indicateurs et actions automatisées. Activez le mode Agent pour exécuter une tâche.",
        default_language="fr",
        allowed_roles="admin",
        tool_ids=_ADMIN_TOOLS,
        max_output_tokens=2048,
    )

    collection_ids_client: list[int] = []
    collection_ids_admin: list[int] = []

    for lang in ("fr", "en"):
        rows = _load_knowledge_file(lang)
        if not rows:
            continue
        coll_client = _upsert_collection(
            db,
            gpt=client,
            slug=f"fedex-kb-{lang}",
            title=f"FedEx Knowledge Base ({lang})",
            language=lang,
        )
        coll_admin = _upsert_collection(
            db,
            gpt=admin,
            slug=f"fedex-kb-admin-{lang}",
            title=f"FedEx Ops KB ({lang})",
            language=lang,
        )
        _ingest_chunks(db, coll_client, rows)
        _ingest_chunks(db, coll_admin, rows)
        collection_ids_client.append(coll_client.id)
        collection_ids_admin.append(coll_admin.id)

    client.knowledge_collection_ids_json = json.dumps(collection_ids_client)
    admin.knowledge_collection_ids_json = json.dumps(collection_ids_admin)
    db.commit()

    try:
        from app.services.gpt.document_ingestion_service import reindex_chunks_without_embeddings

        indexed = reindex_chunks_without_embeddings(db, limit=500)
        if indexed:
            logger.info("Embeddings KB FedEx : %s chunks indexés", indexed)
    except Exception:
        logger.exception("Reindex embeddings seed ignoré")

    logger.info(
        "GPT platform seed OK — client collections=%s admin collections=%s",
        len(collection_ids_client),
        len(collection_ids_admin),
    )
