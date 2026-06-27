from __future__ import annotations

import logging
import re
from io import BytesIO

from jarvis.providers.documents.tesseract_config import (
    configure_pytesseract,
    resolve_ocr_langs,
)
from jarvis.kernel.settings import settings

logger = logging.getLogger(__name__)

_VISION_REQUEST_RE = re.compile(
    r"\b("
    r"décris|decris|décrire|decrire|"
    r"qu'?est[- ]ce que tu vois|que vois[- ]tu|"
    r"analyse cette (photo|image)|analyse l'?image|"
    r"what do you see|describe this (image|photo)|"
    r"décris cette image|decris cette image"
    r")\b",
    re.I,
)

_VISION_MODEL_HINT = (
    "Le modèle actuel llama3.2:3b ne supporte pas la vision. "
    "Je peux seulement lire le texte visible avec OCR. "
    "Pour une vraie analyse image, il faut utiliser llama3.2-vision:11b ou llava."
)


def is_visual_analysis_request(question: str) -> bool:
    return bool(_VISION_REQUEST_RE.search(question or ""))


def vision_model_unavailable_message() -> str:
    return _VISION_MODEL_HINT


def ocr_image_bytes(data: bytes, *, mime_type: str = "image/png") -> str:
    """OCR local — extrait uniquement le texte visible."""
    if not configure_pytesseract(
        tesseract_cmd=settings.tesseract_cmd,
        tessdata_prefix=settings.tessdata_prefix,
    ):
        raise RuntimeError(
            "Tesseract introuvable. Installez Tesseract et lancez scripts/setup_tesseract_langs.py"
        )

    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError(
            "pytesseract requis pour l'OCR. Installez aussi le binaire Tesseract."
        ) from exc

    try:
        img = Image.open(BytesIO(data))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        lang = resolve_ocr_langs(settings.ocr_languages)
        text = pytesseract.image_to_string(img, lang=lang)
        return (text or "").strip()
    except Exception as exc:
        logger.warning("OCR échoué: %s", exc)
        return ""


def read_image(
    data: bytes,
    *,
    file_name: str = "image.png",
    mime_type: str = "image/png",
    question: str = "",
) -> tuple[str, dict[str, str], list[str]]:
    """OCR image ; avertit si l'utilisateur demande une analyse visuelle."""
    warnings: list[str] = []
    metadata = {"mime_type": mime_type, "ocr": True}

    if is_visual_analysis_request(question):
        warnings.append(_VISION_MODEL_HINT)

    ocr_text = ocr_image_bytes(data, mime_type=mime_type)
    if ocr_text:
        extracted = f"Texte OCR extrait de {file_name}:\n{ocr_text}"
        if is_visual_analysis_request(question):
            warnings.append(
                "Cette image ne peut pas être analysée visuellement avec llama3.2:3b, "
                "mais j'ai extrait le texte visible."
            )
    else:
        extracted = f"[Aucun texte OCR détecté dans {file_name}]"
        warnings.append(
            "OCR vide — vérifiez que Tesseract est installé ou que l'image contient du texte lisible."
        )

    logger.info("Image OCR file=%s chars=%s", file_name, len(ocr_text))
    return extracted, metadata, warnings
