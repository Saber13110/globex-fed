"""Embeddings Gemini pour RAG vectoriel (Phase 3)."""

from __future__ import annotations

import logging
from typing import Literal

import httpx

from app.core.config import get_settings
from app.services.llm.providers import gemini_auth_headers

logger = logging.getLogger(__name__)

EmbedTask = Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"]


class EmbeddingError(Exception):
    pass


def _embed_endpoint(model: str) -> str:
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents"


def _model_candidates() -> list[str]:
    settings = get_settings()
    models: list[str] = []
    for raw in [settings.gemini_embedding_model, *settings.gemini_embedding_fallback_models.split(",")]:
        name = raw.strip()
        if name and name not in models:
            models.append(name)
    return models or ["gemini-embedding-001"]


def _embed_batch(
    client: httpx.Client,
    *,
    model: str,
    batch: list[str],
    task_type: EmbedTask,
    api_key: str,
    output_dimensions: int,
) -> list[list[float]]:
    body = {
        "requests": [
            {
                "model": f"models/{model}",
                "content": {"parts": [{"text": text}]},
                "taskType": task_type,
                "outputDimensionality": output_dimensions,
            }
            for text in batch
        ]
    }
    url = _embed_endpoint(model)
    resp = client.post(url, headers=gemini_auth_headers(api_key), json=body)
    if resp.status_code == 429:
        from app.services.llm.gemini_budget import mark_gemini_quota_exhausted

        mark_gemini_quota_exhausted()
    resp.raise_for_status()
    data = resp.json()
    embeddings = data.get("embeddings")
    if not isinstance(embeddings, list):
        raise EmbeddingError("Réponse embeddings Gemini invalide.")

    out: list[list[float]] = []
    for item in embeddings:
        values = item.get("values") if isinstance(item, dict) else None
        if not isinstance(values, list) or not values:
            raise EmbeddingError("Vecteur embedding vide.")
        out.append([float(v) for v in values])
    if len(out) != len(batch):
        raise EmbeddingError("Nombre d'embeddings incohérent avec le batch.")
    return out


def embed_texts(
    texts: list[str],
    *,
    task_type: EmbedTask = "RETRIEVAL_DOCUMENT",
) -> list[list[float]]:
    """Génère des embeddings Gemini pour une liste de textes (batch 16)."""
    from app.services.llm.gemini_budget import is_global_gemini_quota_exhausted

    if is_global_gemini_quota_exhausted():
        raise EmbeddingError("Embeddings ignorés — quota Gemini en cooldown global.")

    settings = get_settings()
    api_key = (settings.gemini_api_key or "").strip()
    if not api_key:
        raise EmbeddingError("Clé API Gemini absente pour les embeddings.")

    cleaned = [(t or "").strip()[:2048] for t in texts if (t or "").strip()]
    if not cleaned:
        return []

    output_dimensions = max(128, min(settings.gemini_embedding_dimensions, 3072))
    out: list[list[float]] = []
    batch_size = 16
    timeout = httpx.Timeout(connect=10.0, read=60.0, write=15.0, pool=5.0)
    models = _model_candidates()
    last_error: Exception | None = None

    with httpx.Client(timeout=timeout) as client:
        for start in range(0, len(cleaned), batch_size):
            batch = cleaned[start : start + batch_size]
            batch_vectors: list[list[float]] | None = None
            for model in models:
                try:
                    batch_vectors = _embed_batch(
                        client,
                        model=model,
                        batch=batch,
                        task_type=task_type,
                        api_key=api_key,
                        output_dimensions=output_dimensions,
                    )
                    if model != models[0]:
                        logger.info("Embeddings OK avec le modèle de secours %s", model)
                    break
                except Exception as exc:
                    last_error = exc
                    logger.warning("Embeddings échoués avec %s : %s", model, exc)
            if batch_vectors is None:
                raise EmbeddingError(f"Échec embeddings Gemini : {last_error}") from last_error
            out.extend(batch_vectors)

    return out


def embed_query(text: str) -> list[float]:
    vectors = embed_texts([text], task_type="RETRIEVAL_QUERY")
    if not vectors:
        raise EmbeddingError("Embedding requête vide.")
    return vectors[0]
