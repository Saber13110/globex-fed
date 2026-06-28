"""Couche assistant IA entreprise Globex FedEx."""

from app.services.ai_assistant.admin_ai_service import AdminAiService, run_admin_ai_query
from app.services.ai_assistant.response_builder import (
    build_error_fallback_response,
    enrich_copilot_response,
)

__all__ = [
    "AdminAiService",
    "run_admin_ai_query",
    "build_error_fallback_response",
    "enrich_copilot_response",
]
