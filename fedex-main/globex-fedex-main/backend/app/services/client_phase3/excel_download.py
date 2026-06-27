"""Excel client — blob + spec export_download (miroir pdf_text.build_text_pdf_download)."""

from __future__ import annotations

from typing import Any

from app.services.ai_assistant.export_dataset_cache import store_client_excel_blob
from app.services.copilot_export_service import build_export_download_spec


def build_excel_download(
    user_id: int,
    xlsx_bytes: bytes,
    *,
    filename: str,
    session_id: int,
) -> dict[str, Any]:
    """Stocke le blob Excel et retourne la spec export_download."""
    if not xlsx_bytes:
        raise ValueError(
            "Impossible de générer le fichier Excel. Réessayez ou reformulez votre demande."
        )
    token = store_client_excel_blob(
        user_id=user_id,
        xlsx_bytes=xlsx_bytes,
        filename=filename,
        meta={"bytes_len": len(xlsx_bytes)},
    )
    return build_export_download_spec(
        preset="text_xlsx",
        filename=filename,
        fmt="xlsx",
        export_token=token,
        session_id=session_id,
    )
