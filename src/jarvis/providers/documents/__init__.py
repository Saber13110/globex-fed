"""Ingestion de fichiers → texte pour LLM text-only (Ollama llama3.2:3b)."""

from jarvis.providers.documents.context_builder import build_context_from_file, select_context_for_question
from jarvis.providers.documents.file_ingestion import ingest_file
from jarvis.providers.documents.ollama_service import ask_llama
from jarvis.providers.documents.types import FileContext

__all__ = [
    "FileContext",
    "ask_llama",
    "build_context_from_file",
    "ingest_file",
    "select_context_for_question",
]
