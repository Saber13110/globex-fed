"""Routes admin — base de connaissances GPT (Phase 3)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from app.core.config import get_settings
from app.models.user import User
from app.routes.deps import get_db, require_role
from app.schemas.gpt_knowledge import (
    GptKnowledgeOverviewResponse,
    KnowledgeCollectionItem,
    KnowledgeDocumentItem,
    KnowledgeReindexResponse,
    KnowledgeUploadResponse,
)
from app.services.gpt.document_ingestion_service import DocumentIngestError
from app.services.gpt.gpt_knowledge_admin_service import (
    delete_document,
    list_collections,
    list_documents,
    list_gpt_knowledge_overview,
    run_reindex,
    upload_document,
)
from sqlalchemy.orm import Session

router = APIRouter(prefix="/gpt/knowledge", tags=["gpt-knowledge"])


@router.get("/overview", response_model=GptKnowledgeOverviewResponse)
def knowledge_overview(
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> GptKnowledgeOverviewResponse:
    return GptKnowledgeOverviewResponse(**list_gpt_knowledge_overview(db))


@router.get("/collections", response_model=list[KnowledgeCollectionItem])
def knowledge_collections(
    gpt_slug: str,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> list[KnowledgeCollectionItem]:
    try:
        return [KnowledgeCollectionItem(**row) for row in list_collections(db, gpt_slug=gpt_slug)]
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/documents", response_model=list[KnowledgeDocumentItem])
def knowledge_documents(
    gpt_slug: str,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> list[KnowledgeDocumentItem]:
    try:
        return [KnowledgeDocumentItem(**row) for row in list_documents(db, gpt_slug=gpt_slug)]
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/upload", response_model=KnowledgeUploadResponse)
async def knowledge_upload(
    file: UploadFile = File(...),
    gpt_slug: str = Form(default="fedex-admin-ops"),
    language: str = Form(default="fr"),
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> KnowledgeUploadResponse:
    settings = get_settings()
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nom de fichier requis.")

    data = await file.read()
    max_bytes = settings.knowledge_upload_max_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Fichier trop volumineux (max {settings.knowledge_upload_max_mb} Mo).",
        )

    try:
        result = upload_document(
            db,
            gpt_slug=gpt_slug,
            file_bytes=data,
            filename=file.filename,
            language=language.strip().lower()[:8] or "fr",
            uploaded_by_user_id=admin.id,
        )
        return KnowledgeUploadResponse(**result)
    except DocumentIngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Indexation échouée : {exc}",
        ) from exc


@router.post("/reindex", response_model=KnowledgeReindexResponse)
def knowledge_reindex(
    gpt_slug: str | None = Query(default=None),
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> KnowledgeReindexResponse:
    try:
        return KnowledgeReindexResponse(**run_reindex(db, gpt_slug=gpt_slug))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def knowledge_delete_document(
    document_id: int,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> None:
    if not delete_document(db, document_id=document_id):
        raise HTTPException(status_code=404, detail="Document introuvable.")
