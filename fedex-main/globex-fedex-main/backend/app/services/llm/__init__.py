"""Package LLM — Gemini principal, Ollama secours."""

from app.services.llm.orchestrator import (
    LlmChatResult,
    generate_response,
    generate_session_title,
    generate_support_reply,
)
from app.services.llm.intent_detection import detect_intent
from app.services.llm.tracking_extract import extract_tracking_number
from app.services.llm.fedex_context import fetch_fedex_tracking_data

__all__ = [
    "LlmChatResult",
    "detect_intent",
    "extract_tracking_number",
    "fetch_fedex_tracking_data",
    "generate_response",
    "generate_support_reply",
    "generate_session_title",
]
