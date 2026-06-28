from __future__ import annotations

import logging
from pathlib import Path

from jarvis.providers.documents.excel_reader import read_csv, read_excel
from jarvis.providers.documents.image_ocr_reader import read_image
from jarvis.providers.documents.pdf_reader import read_pdf
from jarvis.providers.documents.types import FileContext

logger = logging.getLogger(__name__)

_TEXT_EXTENSIONS = {".txt", ".md"}
_CSV_EXTENSIONS = {".csv"}
_EXCEL_EXTENSIONS = {".xlsx", ".xls"}
_PDF_EXTENSIONS = {".pdf"}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

_MIME_TO_EXT = {
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/csv": ".csv",
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-excel": ".xls",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


class UnsupportedFileTypeError(ValueError):
    pass


def detect_file_type(filename: str, mime_type: str | None = None) -> str:
    ext = Path(filename).suffix.lower()
    if ext:
        return ext
    if mime_type and mime_type in _MIME_TO_EXT:
        return _MIME_TO_EXT[mime_type]
    return ""


def ingest_file(
    data: bytes,
    *,
    filename: str,
    mime_type: str | None = None,
    question: str = "",
) -> FileContext:
    """Point d'entrée : détecte le type et extrait le texte structuré."""
    if not data:
        raise ValueError("Fichier vide.")

    file_type = detect_file_type(filename, mime_type)
    warnings: list[str] = []
    metadata: dict = {"size_bytes": len(data)}
    extracted = ""

    if file_type in _TEXT_EXTENSIONS:
        extracted = _read_plain_text(data)
        metadata["encoding"] = "utf-8/latin-1"
    elif file_type in _CSV_EXTENSIONS:
        extracted, metadata, warnings = read_csv(data, file_name=filename)
    elif file_type in _EXCEL_EXTENSIONS:
        extracted, metadata, warnings = read_excel(data, file_name=filename)
        sheets = metadata.get("sheets") or []
        if sheets:
            warnings.insert(
                0,
                f"Ce fichier Excel contient les feuilles suivantes : {', '.join(sheets)}.",
            )
    elif file_type in _PDF_EXTENSIONS:
        extracted, metadata, warnings = read_pdf(data, file_name=filename)
        if extracted:
            warnings.insert(0, "J'ai extrait le texte du PDF.")
    elif file_type in _IMAGE_EXTENSIONS:
        mt = mime_type or _ext_to_mime(file_type)
        extracted, metadata, warnings = read_image(
            data, file_name=filename, mime_type=mt, question=question,
        )
    else:
        raise UnsupportedFileTypeError(
            f"Type non supporté : {file_type or 'inconnu'}. "
            "Formats : txt, md, csv, xlsx, xls, pdf, png, jpg, jpeg, webp."
        )

    logger.info("Ingestion OK file=%s type=%s chars=%s", filename, file_type, len(extracted))
    return FileContext(
        file_name=filename,
        file_type=file_type,
        extracted_text=extracted,
        metadata=metadata,
        warnings=list(dict.fromkeys(warnings)),
    )


def _read_plain_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _ext_to_mime(ext: str) -> str:
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(ext, "application/octet-stream")
