"""Découpage de texte pour indexation KB."""

from __future__ import annotations

import re


def split_text(
    text: str,
    *,
    chunk_size: int = 900,
    overlap: int = 150,
) -> list[str]:
    """Découpe un texte long en fragments avec chevauchement."""
    raw = re.sub(r"\r\n?", "\n", (text or "").strip())
    if not raw:
        return []

    chunk_size = max(200, chunk_size)
    overlap = min(max(0, overlap), chunk_size // 2)

    paragraphs = [p.strip() for p in re.split(r"\n{2,}", raw) if p.strip()]
    if not paragraphs:
        paragraphs = [raw]

    chunks: list[str] = []
    current = ""

    def _flush() -> None:
        nonlocal current
        piece = current.strip()
        if piece:
            chunks.append(piece)
        current = ""

    for para in paragraphs:
        if len(para) <= chunk_size:
            candidate = f"{current}\n\n{para}".strip() if current else para
            if len(candidate) <= chunk_size:
                current = candidate
            else:
                _flush()
                current = para
            continue

        sentences = re.split(r"(?<=[.!?])\s+", para)
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(sentence) > chunk_size:
                _flush()
                for i in range(0, len(sentence), chunk_size - overlap):
                    chunks.append(sentence[i : i + chunk_size])
                continue
            candidate = f"{current} {sentence}".strip() if current else sentence
            if len(candidate) <= chunk_size:
                current = candidate
            else:
                _flush()
                current = sentence

    _flush()

    if overlap > 0 and len(chunks) > 1:
        merged: list[str] = []
        prev_tail = ""
        for chunk in chunks:
            if prev_tail:
                merged.append(f"{prev_tail}\n{chunk}".strip()[: chunk_size + overlap])
            else:
                merged.append(chunk)
            prev_tail = chunk[-overlap:] if len(chunk) > overlap else chunk
        return merged

    return chunks
