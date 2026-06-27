from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from jarvis.providers.documents.context_builder import build_context_from_file, merge_context_payload
from jarvis.providers.documents.file_ingestion import UnsupportedFileTypeError
from jarvis.providers.documents.image_ocr_reader import is_visual_analysis_request, vision_model_unavailable_message
from jarvis.providers.documents.ollama_service import ask_llama, format_assistant_preamble
from jarvis.providers.documents.types import FileContext

router = APIRouter()


class IngestResponse(BaseModel):
    file_name: str
    file_type: str
    extracted_preview: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    char_count: int = 0


class AskWithFileResponse(BaseModel):
    reply: str
    preamble: str = ""
    warnings: list[str] = Field(default_factory=list)
    file_name: str = ""
    file_type: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    context_truncated: bool = False


async def _read_upload(upload: UploadFile) -> tuple[bytes, str, str | None]:
    data = await upload.read()
    filename = upload.filename or "document"
    return data, filename, upload.content_type


@router.get("/api/assistant/health")
async def assistant_health() -> dict[str, str]:
    return {"status": "ok", "routes": "ingest,ask-with-file,ask"}


@router.post("/api/assistant/ingest", response_model=IngestResponse)
async def assistant_ingest_file(
    file: UploadFile = File(...),  # noqa: B008
    question: str = Form(""),
) -> IngestResponse:
    """Extrait le texte d'un fichier sans appeler Ollama."""
    data, filename, mime = await _read_upload(file)
    try:
        ctx = build_context_from_file(data, filename=filename, mime_type=mime, question=question)
    except UnsupportedFileTypeError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    preview = ctx.extracted_text[:4000]
    if len(ctx.extracted_text) > 4000:
        preview += "\n… [tronqué pour l'aperçu]"

    return IngestResponse(
        file_name=ctx.file_name,
        file_type=ctx.file_type,
        extracted_preview=preview,
        metadata=ctx.metadata,
        warnings=ctx.warnings,
        char_count=len(ctx.extracted_text),
    )


@router.post("/api/assistant/ask-with-file", response_model=AskWithFileResponse)
async def assistant_ask_with_file(
    file: UploadFile = File(...),  # noqa: B008
    question: str = Form(..., min_length=1, max_length=8000),
) -> AskWithFileResponse:
    """Ingère le fichier (texte uniquement), puis pose la question à Ollama."""
    data, filename, mime = await _read_upload(file)

    if is_visual_analysis_request(question):
        return AskWithFileResponse(
            reply=vision_model_unavailable_message(),
            preamble=vision_model_unavailable_message(),
            warnings=[vision_model_unavailable_message()],
            file_name=filename,
        )

    try:
        file_ctx = build_context_from_file(data, filename=filename, mime_type=mime, question=question)
    except UnsupportedFileTypeError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    context = merge_context_payload(file_ctx, question)
    preamble = format_assistant_preamble(context)

    try:
        answer = await ask_llama(question, context)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"Ollama indisponible : {exc}") from exc

    full_reply = answer
    if preamble:
        full_reply = f"{preamble}\n\n{answer}"

    return AskWithFileResponse(
        reply=full_reply,
        preamble=preamble,
        warnings=list(file_ctx.warnings),
        file_name=file_ctx.file_name,
        file_type=file_ctx.file_type,
        metadata=file_ctx.metadata,
        context_truncated=bool(context.get("truncated")),
    )


class AskWithContextRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=8000)
    context: FileContext


@router.post("/api/assistant/ask", response_model=AskWithFileResponse)
async def assistant_ask_with_context(body: AskWithContextRequest) -> AskWithFileResponse:
    """Pose une question sur un contexte déjà ingéré (JSON)."""
    if is_visual_analysis_request(body.question):
        return AskWithFileResponse(
            reply=vision_model_unavailable_message(),
            preamble=vision_model_unavailable_message(),
            warnings=[vision_model_unavailable_message()],
            file_name=body.context.file_name,
            file_type=body.context.file_type,
        )

    context = merge_context_payload(body.context, body.question)
    preamble = format_assistant_preamble(context)
    try:
        answer = await ask_llama(body.question, context)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"Ollama indisponible : {exc}") from exc

    full_reply = f"{preamble}\n\n{answer}" if preamble else answer
    return AskWithFileResponse(
        reply=full_reply,
        preamble=preamble,
        warnings=body.context.warnings,
        file_name=body.context.file_name,
        file_type=body.context.file_type,
        metadata=body.context.metadata,
        context_truncated=bool(context.get("truncated")),
    )
