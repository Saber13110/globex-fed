from datetime import datetime

from pydantic import BaseModel, Field


class GptKnowledgeProfileItem(BaseModel):
    slug: str
    name: str
    collections: int
    chunks: int
    embedded_chunks: int
    documents: int


class GptKnowledgeOverviewResponse(BaseModel):
    gpt_profiles: list[GptKnowledgeProfileItem]


class KnowledgeCollectionItem(BaseModel):
    id: int
    slug: str
    title: str
    language: str
    source_type: str
    chunk_count: int
    document_count: int


class KnowledgeDocumentItem(BaseModel):
    id: int
    collection_id: int
    original_filename: str
    file_size_bytes: int
    status: str
    chunk_count: int
    error_message: str | None = None
    created_at: datetime | None = None


class KnowledgeUploadResponse(BaseModel):
    document_id: int
    filename: str
    status: str
    chunk_count: int


class KnowledgeReindexResponse(BaseModel):
    reindexed: int
