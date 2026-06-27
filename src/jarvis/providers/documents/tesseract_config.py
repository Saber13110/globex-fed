"""Configuration Tesseract / pytesseract pour Windows et Linux."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_PROJECT_TESSDATA = _PROJECT_ROOT / "tessdata"

_WINDOWS_CANDIDATES = (
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
)

_configured = False


def resolve_tesseract_cmd(explicit: str = "") -> str | None:
    if explicit.strip():
        p = Path(explicit.strip())
        return str(p) if p.is_file() else explicit.strip()
    for candidate in _WINDOWS_CANDIDATES:
        if candidate.is_file():
            return str(candidate)
    found = shutil.which("tesseract")
    return found


def resolve_tessdata_dir(explicit_prefix: str = "") -> Path | None:
    """Retourne le dossier tessdata (fichiers *.traineddata)."""
    if explicit_prefix.strip():
        p = Path(explicit_prefix.strip())
        if not p.is_absolute():
            p = _PROJECT_ROOT / p
        if p.is_dir() and any(p.glob("*.traineddata")):
            return p
        child = p / "tessdata"
        if child.is_dir() and any(child.glob("*.traineddata")):
            return child

    if _PROJECT_TESSDATA.is_dir() and any(_PROJECT_TESSDATA.glob("*.traineddata")):
        return _PROJECT_TESSDATA

    for exe in _WINDOWS_CANDIDATES:
        td = exe.parent / "tessdata"
        if td.is_dir() and any(td.glob("*.traineddata")):
            return td

    found = shutil.which("tesseract")
    if found:
        td = Path(found).parent / "tessdata"
        if td.is_dir():
            return td
    return None


def list_available_langs(tessdata_dir: Path | None = None) -> set[str]:
    td = tessdata_dir or resolve_tessdata_dir()
    if not td:
        return set()
    return {p.stem for p in td.glob("*.traineddata")}


def resolve_ocr_langs(requested: str = "fra+eng", tessdata_dir: Path | None = None) -> str:
    available = list_available_langs(tessdata_dir)
    if not available:
        return "eng"
    picked = [lang for lang in requested.split("+") if lang in available]
    if picked:
        return "+".join(picked)
    if "eng" in available:
        return "eng"
    return sorted(available)[0]


def configure_pytesseract(*, tesseract_cmd: str = "", tessdata_prefix: str = "") -> bool:
    """Configure pytesseract une fois ; retourne False si binaire introuvable."""
    global _configured
    if _configured:
        return True

    cmd = resolve_tesseract_cmd(tesseract_cmd)
    if not cmd or not Path(cmd).is_file():
        logger.warning("Tesseract introuvable — OCR désactivé.")
        return False

    tessdata = resolve_tessdata_dir(tessdata_prefix)
    if tessdata:
        # TESSDATA_PREFIX = répertoire parent contenant le dossier tessdata
        os.environ["TESSDATA_PREFIX"] = str(tessdata.parent)

    try:
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = cmd
        _configured = True
        langs = list_available_langs(tessdata)
        logger.info(
            "Tesseract OK cmd=%s langs=%s ocr=%s",
            cmd,
            sorted(langs),
            resolve_ocr_langs(tessdata_dir=tessdata),
        )
        return True
    except ImportError:
        logger.warning("pytesseract non installé — pip install pytesseract")
        return False
