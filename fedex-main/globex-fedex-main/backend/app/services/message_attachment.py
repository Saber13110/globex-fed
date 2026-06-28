"""Encodage de pièces jointes dans message_text (sans migration SQL)."""

from __future__ import annotations

import json
from typing import Any

_MARKER = "[[GLOBEX_ATTACHMENT:"
_MARKER_END = "]]"

_IMAGE_MIME = frozenset(
    {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
        "image/gif",
    }
)

_DOCUMENT_MIME = frozenset(
    {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    }
)

_ALLOWED_MIME = _IMAGE_MIME | _DOCUMENT_MIME


def normalize_image_mime(mime: str | None) -> str | None:
    if not mime:
        return None
    m = mime.strip().lower()
    if m == "image/jpg":
        return "image/jpeg"
    return m if m in _IMAGE_MIME else None


def normalize_attachment_mime(mime: str | None) -> str | None:
    if not mime:
        return None
    m = mime.strip().lower()
    if m == "image/jpg":
        return "image/jpeg"
    return m if m in _ALLOWED_MIME else None


def pack_message_text(
    text: str,
    *,
    image_base64: str | None,
    image_mime_type: str | None,
    file_name: str | None = None,
) -> str:
    """Préfixe JSON pour persister la pièce jointe avec le message utilisateur."""
    caption = (text or "").strip()
    if not image_base64:
        return caption
    mime = normalize_attachment_mime(image_mime_type)
    if not mime:
        return caption
    kind = "image" if mime.startswith("image/") else "document"
    payload_obj: dict[str, Any] = {"mime": mime, "b64": image_base64, "kind": kind}
    if file_name and file_name.strip():
        payload_obj["name"] = file_name.strip()
    payload = json.dumps(payload_obj, separators=(",", ":"))
    if caption:
        return f"{_MARKER}{payload}{_MARKER_END}\n{caption}"
    return f"{_MARKER}{payload}{_MARKER_END}"


def unpack_message_text(raw: str) -> tuple[str, str | None, str | None]:
    """Retourne (texte affiché, base64, mime)."""
    text, b64, mime, _, _ = _unpack_attachment_payload(raw)
    return text, b64, mime


def unpack_message_attachment(
    raw: str,
) -> tuple[str, str | None, str | None, str | None, str | None]:
    """Retourne (texte affiché, base64, mime, file_name, kind)."""
    return _unpack_attachment_payload(raw)


def _unpack_attachment_payload(
    raw: str,
) -> tuple[str, str | None, str | None, str | None, str | None]:
    if not raw.startswith(_MARKER):
        return raw, None, None, None, None
    end = raw.find(_MARKER_END)
    if end < 0:
        return raw, None, None, None, None
    try:
        payload: dict[str, Any] = json.loads(raw[len(_MARKER) : end])
    except json.JSONDecodeError:
        return raw, None, None, None, None
    mime = normalize_attachment_mime(str(payload.get("mime") or ""))
    b64 = payload.get("b64")
    if not mime or not isinstance(b64, str) or not b64.strip():
        return raw, None, None, None, None
    name_raw = payload.get("name")
    name = str(name_raw).strip() if isinstance(name_raw, str) and name_raw.strip() else None
    kind_raw = payload.get("kind")
    if isinstance(kind_raw, str) and kind_raw.strip():
        kind = kind_raw.strip()
    elif mime.startswith("image/"):
        kind = "image"
    else:
        kind = "document"
    rest = raw[end + len(_MARKER_END) :].lstrip("\n")
    return rest, b64.strip(), mime, name, kind


def image_data_url(mime: str, base64_data: str) -> str:
    return f"data:{mime};base64,{base64_data}"
