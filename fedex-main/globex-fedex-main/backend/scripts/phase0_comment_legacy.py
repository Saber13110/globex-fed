"""Phase 0 — commente le code legacy et ajoute les stubs ACTIVE."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "app" / "services"

BANNER = """# =============================================================================
# LEGACY DESACTIVE — refonte client_agent v2 (Phase 0)
# Ne pas réactiver sans retirer le bloc ACTIVE ci-dessous.
# =============================================================================
"""

ACTIVE_SEP = """
# =============================================================================
# ACTIVE — Phase 0 stub
# =============================================================================
"""


def comment_lines(content: str) -> str:
    lines = content.splitlines()
    return "\n".join(f"# {line}" if line else "#" for line in lines)


def apply_full_comment(path: Path, active_stub: str) -> None:
    original = path.read_text(encoding="utf-8")
    path.write_text(BANNER + comment_lines(original) + ACTIVE_SEP + active_stub.strip() + "\n", encoding="utf-8")
    print(f"commented: {path.name}")


def apply_partial_comment(path: Path, keep_ranges: list[tuple[int, int]], active_stub: str = "") -> None:
    """keep_ranges: list of (start, end) 1-based inclusive line numbers to keep active."""
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[str] = [BANNER.rstrip()]
    for i, line in enumerate(lines, start=1):
        keep = any(start <= i <= end for start, end in keep_ranges)
        out.append(line if keep else (f"# {line}" if line else "#"))
    if active_stub:
        out.append(ACTIVE_SEP.rstrip())
        out.append(active_stub.strip())
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"partial comment: {path.name}")


CHATBOT_PHASE0_ACTIVE = '''
"""Chat client — stub Phase 0 (maintenance, sans client_agent)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage, MessageSender
from app.models.chat_session import ChatSession
from app.models.user import User
from app.core.config import get_settings
from app.services.llm.session_title import heuristic_session_title, should_auto_rename
from app.services.message_attachment import normalize_image_mime, pack_message_text
from app.services.prompt_guard_service import assess_user_message, must_block_preferences
from app.services.llm.prompts import prompt_injection_refusal

logger = logging.getLogger(__name__)

_MAINTENANCE = {
    "fr": "L'assistant FedEx est en cours de reconstruction. Réessayez bientôt.",
    "en": "The FedEx assistant is being rebuilt. Please try again soon.",
}


def _phase0_maintenance_reply(ui_language: str | None, user: User) -> str:
    lang = (ui_language or user.preferred_language or "fr").lower()
    return _MAINTENANCE.get(lang[:2], _MAINTENANCE["fr"])


def _base_result(
    reply: str,
    session: ChatSession,
    *,
    shipment: dict[str, Any] | None = None,
    source: str,
    intent: str,
    tracking_number: str | None,
    llm_provider: str | None,
) -> dict[str, Any]:
    return {
        "reply": reply,
        "session_id": session.id,
        "session_title": session.title,
        "shipment": shipment,
        "source": source,
        "intent": intent,
        "tracking_number": tracking_number,
        "llm_provider": llm_provider,
    }


def process_user_message(
    db: Session,
    user: User,
    message: str,
    session: ChatSession,
    response_preferences: str | None = None,
    preferred_name: str | None = None,
    ui_language: str | None = None,
    image_base64: str | None = None,
    image_mime_type: str | None = None,
    agent_mode: bool = False,
    agent_flow_id: str | None = None,
    agent_answers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Traite un message utilisateur client — Phase 0 maintenance uniquement."""
    settings = get_settings()
    probe_text = (message or "").strip()
    if settings.prompt_guard_enabled and probe_text and not (image_base64 or "").strip():
        risk = assess_user_message(probe_text)
        if must_block_preferences(risk):
            lang = (ui_language or user.preferred_language or "fr").lower()
            refusal = prompt_injection_refusal(lang)
            return {
                "reply": refusal,
                "session_id": session.id,
                "session_title": session.title,
                "source": "security",
                "intent": "security_blocked",
                "tracking_number": None,
                "llm_provider": None,
                "shipment": None,
                "agent_mode": False,
            }

    try:
        b64 = (image_base64 or "").strip() or None
        mime = normalize_image_mime(image_mime_type) if b64 else None
        stored_message = pack_message_text(message, image_base64=b64, image_mime_type=mime)

        user_msg = ChatMessage(
            session_id=session.id,
            sender=MessageSender.user.value,
            source="user_input",
            message_text=stored_message,
        )
        db.add(user_msg)
        db.flush()

        reply = _phase0_maintenance_reply(ui_language, user)

        bot = ChatMessage(
            session_id=session.id,
            sender=MessageSender.bot.value,
            source="maintenance",
            message_text=reply,
        )
        db.add(bot)

        title_source = message.strip() or ("Image FedEx" if b64 else message)
        if should_auto_rename(session.title):
            session.title = heuristic_session_title(
                title_source,
                ui_language=ui_language,
                intent="phase0",
                tracking_number=None,
            )
        session.updated_at = func.now()
        db.commit()
        db.refresh(bot)

        result = _base_result(
            reply,
            session,
            source="maintenance",
            intent="phase0",
            tracking_number=None,
            llm_provider=None,
        )
        result["agent_mode"] = False
        return result
    except Exception:
        logger.exception("chatbot Phase 0 stub failure")
        db.rollback()
        return {
            "reply": (
                "Désolé, une erreur technique est survenue. "
                "L'assistant est en cours de reconstruction — réessayez dans un instant."
            ),
            "session_id": session.id,
            "session_title": session.title,
            "source": "fallback",
            "intent": "error",
            "tracking_number": None,
            "llm_provider": None,
            "shipment": None,
            "agent_mode": False,
        }
'''

CLIENT_AGENT_ROOT = ROOT / "client_agent"

CLIENT_AGENT_INIT_ACTIVE = '''"""Package client_agent — stub Phase 0."""

__all__ = []
'''

CLIENT_AGENT_TYPES_ACTIVE = '''"""Types client_agent — stub Phase 0."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ClientTurnResult:
    reply: str
    source: str
    intent: str
    tracking_number: str | None = None
    llm_provider: str | None = None
    shipment: dict[str, Any] | None = None
    agent_mode: bool | None = field(default=None)
    export_download: dict[str, Any] | None = None
    tools_used: list[str] | None = None
'''

CLIENT_AGENT_KERNEL_ACTIVE = '''"""Noyau client_agent — stub Phase 0."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.chat_session import ChatSession
from app.models.user import User
from app.services.client_agent.types import ClientTurnResult


def run_turn(
    db: Session,
    user: User,
    message: str,
    session: ChatSession,
    **kwargs: Any,
) -> ClientTurnResult:
    raise RuntimeError("Phase 0 — assistant client desactive")
'''

CLIENT_AGENT_MODULE_ACTIVE = '''"""client_agent — stub Phase 0."""
'''

TURN_ROUTER_ACTIVE = '''"""Routeur client — stub Phase 0."""
'''

VALIDATOR_ACTIVE = '''"""Validateur client — stub Phase 0."""

from __future__ import annotations

from typing import Any


def should_validate_turn(turn_type: str | None) -> bool:
    return False


def validate_client_reply(
    reply: str,
    *,
    message: str,
    fedex_context_json: str | None,
    tool_payloads: list[dict[str, Any]] | None = None,
    intent: str | None = None,
    ui_language: str | None = None,
    preferred_name: str | None = None,
    tools_used: list[str] | None = None,
    turn_type: str | None = None,
) -> tuple[str, bool, str | None]:
    return reply, False, None
'''

CONVERSATIONAL_ACTIVE = '''"""Messages conversationnels client — stub Phase 0."""
'''

REPLY_SAFETY_ACTIVE = '''"""Sécurité réponses client — stub Phase 0."""


def repair_client_tracking_reply(reply: str, **kwargs) -> str:
    return reply or ""


def is_generic_tracking_boilerplate(reply: str, **kwargs) -> bool:
    return False
'''

AGENT_SERVICE_ACTIVE = '''"""Agent client — stub Phase 0."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User

TASK_PICKER = "task_picker"
TASK_TRACK = "track_package"


def should_route_to_client_agent(message: str) -> bool:
    return False


def open_client_support_ticket(
    db: Session,
    *,
    user: User,
    message: str,
    tracking_number: str | None = None,
    category: str = "delivery",
    priority: str = "medium",
    subject_prefix: str = "[Agent]",
) -> dict[str, Any]:
    raise RuntimeError("Assistant en reconstruction")
'''

CHAT_MOCK_ACTIVE = '''"""Mock chat client — stub Phase 0."""

from __future__ import annotations

from typing import Any


def try_mock_client_response(*args: Any, **kwargs: Any) -> dict[str, Any] | None:
    return None
'''


def main() -> None:
    apply_full_comment(ROOT / "chatbot_service.py", CHATBOT_PHASE0_ACTIVE)
    apply_full_comment(ROOT / "client_turn_router.py", TURN_ROUTER_ACTIVE)
    apply_full_comment(ROOT / "client_response_validator.py", VALIDATOR_ACTIVE)
    apply_full_comment(ROOT / "client_conversational.py", CONVERSATIONAL_ACTIVE)
    apply_full_comment(ROOT / "client_reply_safety.py", REPLY_SAFETY_ACTIVE)
    apply_full_comment(ROOT / "client_agent_service.py", AGENT_SERVICE_ACTIVE)
    apply_full_comment(ROOT / "client_chat_mock.py", CHAT_MOCK_ACTIVE)

    apply_full_comment(CLIENT_AGENT_ROOT / "__init__.py", CLIENT_AGENT_INIT_ACTIVE)
    apply_full_comment(CLIENT_AGENT_ROOT / "types.py", CLIENT_AGENT_TYPES_ACTIVE)
    apply_full_comment(CLIENT_AGENT_ROOT / "kernel.py", CLIENT_AGENT_KERNEL_ACTIVE)
    for name in (
        "tool_bridge.py",
        "ollama_bridge.py",
        "routing.py",
        "facts.py",
        "history.py",
        "export_turn.py",
        "export_routing.py",
        "guard.py",
        "shipment_turn.py",
        "capabilities.py",
        "stage.py",
        "pdf_compose.py",
    ):
        apply_full_comment(CLIENT_AGENT_ROOT / name, CLIENT_AGENT_MODULE_ACTIVE)

    # Garder _gemini_agent_call + verify_agent_result (admin) — lignes alignées sur client_agent_brain.py
    apply_partial_comment(
        ROOT / "client_agent_brain.py",
        keep_ranges=[(1, 73), (177, 226)],
    )


if __name__ == "__main__":
    main()
