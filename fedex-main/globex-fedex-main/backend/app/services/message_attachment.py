"""Encodage d'images dans message_text (sans migration SQL)."""

from __future__ import annotations

import json
import re
from typing import Any

_MARKER = "[[GLOBEX_ATTACHMENT:"
_MARKER_END = "]]"

_ALLOWED_MIME = frozenset(
    {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
        "image/gif",
    }
)


def normalize_image_mime(mime: str | None) -> str | None:
    if not mime:
        return None
    m = mime.strip().lower()
    if m == "image/jpg":
        return "image/jpeg"
    return m if m in _ALLOWED_MIME else None


def pack_message_text(text: str, *, image_base64: str | None, image_mime_type: str | None) -> str:
    """Préfixe JSON pour persister l'image avec le message utilisateur."""
    caption = (text or "").strip()
    if not image_base64 or not image_mime_type:
        return caption
    mime = normalize_image_mime(image_mime_type)
    if not mime:
        return caption
    payload = json.dumps({"mime": mime, "b64": image_base64}, separators=(",", ":"))
    if caption:
        return f"{_MARKER}{payload}{_MARKER_END}\n{caption}"
    return f"{_MARKER}{payload}{_MARKER_END}"


def unpack_message_text(raw: str) -> tuple[str, str | None, str | None]:
    """Retourne (texte affiché, base64, mime)."""
    if not raw.startswith(_MARKER):
        return raw, None, None
    end = raw.find(_MARKER_END)
    if end < 0:
        return raw, None, None
    try:
        payload: dict[str, Any] = json.loads(raw[len(_MARKER) : end])
    except json.JSONDecodeError:
        return raw, None, None
    mime = normalize_image_mime(str(payload.get("mime") or ""))
    b64 = payload.get("b64")
    if not mime or not isinstance(b64, str) or not b64.strip():
        return raw, None, None
    rest = raw[end + len(_MARKER_END) :].lstrip("\n")
    return rest, b64.strip(), mime


def image_data_url(mime: str, base64_data: str) -> str:
    return f"data:{mime};base64,{base64_data}"
