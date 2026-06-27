"""Intégration Jarvis-OS — sidecar LLM pour l'onglet admin Agent Window."""

from app.services.jarvis.agent_window_service import process_agent_window_chat
from app.services.jarvis.bridge import check_jarvis_health, call_jarvis_generate

__all__ = [
    "call_jarvis_generate",
    "check_jarvis_health",
    "process_agent_window_chat",
]
