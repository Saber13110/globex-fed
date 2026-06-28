from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import UploadFile

MAX_SUPPORT_ATTACHMENT_BYTES = 15 * 1024 * 1024
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads" / "support"

BLOCKED_EXTENSIONS = frozenset(
    {
        ".exe",
        ".bat",
        ".cmd",
        ".com",
        ".msi",
        ".scr",
        ".ps1",
        ".sh",
        ".dll",
        ".vbs",
        ".js",
        ".jar",
    }
)


def ensure_upload_dir() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def safe_filename(name: str) -> str:
    base = Path(name).name
    cleaned = re.sub(r"[^\w.\-() ]", "_", base, flags=re.UNICODE).strip("._ ")
    return (cleaned or "file")[:180]


def validate_stored_name(stored_name: str) -> str:
    cleaned = stored_name.strip()
    if not cleaned or ".." in cleaned or "/" in cleaned or "\\" in cleaned:
        raise ValueError("Nom de fichier invalide.")
    if not re.fullmatch(r"[a-f0-9]{32}_[\w.\-() ]+", cleaned):
        raise ValueError("Nom de fichier invalide.")
    return cleaned


def display_filename(stored_name: str) -> str:
    parts = stored_name.split("_", 1)
    return parts[1] if len(parts) == 2 else stored_name


async def save_support_attachment(file: UploadFile) -> str:
    ensure_upload_dir()
    original = file.filename or "file"
    ext = Path(original).suffix.lower()
    if ext in BLOCKED_EXTENSIONS:
        raise ValueError("Type de fichier non autorisé.")

    content = await file.read()
    if not content:
        raise ValueError("Fichier vide.")
    if len(content) > MAX_SUPPORT_ATTACHMENT_BYTES:
        raise ValueError("Fichier trop volumineux (max 15 Mo).")

    stored = f"{uuid.uuid4().hex}_{safe_filename(original)}"
    target = UPLOAD_DIR / stored
    target.write_bytes(content)
    return stored


def attachment_file_path(stored_name: str) -> Path:
    validate_stored_name(stored_name)
    path = UPLOAD_DIR / stored_name
    if not path.is_file():
        raise FileNotFoundError(stored_name)
    return path
