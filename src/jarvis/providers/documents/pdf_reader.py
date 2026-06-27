from __future__ import annotations

import logging
import re
from io import BytesIO
from typing import Any

logger = logging.getLogger(__name__)

_MIN_CHARS_PER_PAGE_FOR_TEXT_PDF = 15


def read_pdf(data: bytes, *, file_name: str = "document.pdf") -> tuple[str, dict[str, Any], list[str]]:
    """Extrait le texte page par page ; OCR si PDF scanné."""
    warnings: list[str] = []
    metadata: dict[str, Any] = {"pages": 0, "ocr_pages": []}

    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise RuntimeError("PyMuPDF (pymupdf) requis pour lire les PDF.") from exc

    doc = fitz.open(stream=data, filetype="pdf")
    metadata["pages"] = doc.page_count
    parts: list[str] = []

    for idx in range(doc.page_count):
        page = doc.load_page(idx)
        page_num = idx + 1
        text = (page.get_text("text") or "").strip()

        if len(text) >= _MIN_CHARS_PER_PAGE_FOR_TEXT_PDF:
            parts.append(f"Page {page_num}:\n{text}")
            continue

        ocr_text = _ocr_pdf_page(page)
        if ocr_text.strip():
            metadata["ocr_pages"].append(page_num)
            parts.append(f"Page {page_num} (OCR):\n{ocr_text.strip()}")
        else:
            parts.append(f"Page {page_num}:\n[aucun texte lisible]")

    doc.close()

    if metadata["ocr_pages"]:
        warnings.append("Ce PDF semble scanné, j'ai utilisé OCR sur certaines pages.")

    full = "\n\n".join(parts).strip()
    if not full:
        warnings.append("Aucun texte extrait du PDF.")
    else:
        logger.info(
            "PDF extrait file=%s pages=%s ocr_pages=%s chars=%s",
            file_name,
            metadata["pages"],
            len(metadata["ocr_pages"]),
            len(full),
        )

    return full, metadata, warnings


def _ocr_pdf_page(page: Any) -> str:
    import fitz

    from jarvis.providers.documents.image_ocr_reader import ocr_image_bytes

    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    return ocr_image_bytes(pix.tobytes("png"), mime_type="image/png")
