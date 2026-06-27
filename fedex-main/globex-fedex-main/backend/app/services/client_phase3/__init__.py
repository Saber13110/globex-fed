"""Phase 3b client — exports post-réponse LLM (PDF + Excel)."""

from app.services.client_phase3.excel_postprocess import (
    handle_excel_only_followup_turn,
    maybe_attach_excel_export,
    wants_excel_format,
)
from app.services.client_phase3.pdf_postprocess import (
    handle_conversation_pdf_turn,
    handle_pdf_only_followup_turn,
    is_pdf_only_followup,
    maybe_attach_pdf_export,
    wants_pdf_format,
)

__all__ = [
    "handle_conversation_pdf_turn",
    "handle_excel_only_followup_turn",
    "handle_pdf_only_followup_turn",
    "is_pdf_only_followup",
    "maybe_attach_excel_export",
    "maybe_attach_pdf_export",
    "wants_excel_format",
    "wants_pdf_format",
]
