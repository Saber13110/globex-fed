"""
Façade LLM — rétrocompatibilité avec les imports existants.
Implémentation : app.services.llm (Gemini Flash + Ollama gemma3).
"""

from app.services.llm import (
    LlmChatResult,
    detect_intent,
    extract_tracking_number,
    fetch_fedex_tracking_data,
    generate_response,
    generate_session_title,
    generate_support_reply,
)

__all__ = [
    "LlmChatResult",
    "detect_intent",
    "extract_tracking_number",
    "fetch_fedex_tracking_data",
    "generate_response",
    "generate_support_reply",
    "generate_session_title",
]
