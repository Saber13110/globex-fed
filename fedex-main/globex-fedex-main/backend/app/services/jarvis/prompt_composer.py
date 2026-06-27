"""Assemblage du message envoyé à Jarvis."""

from __future__ import annotations

from app.schemas.agent_window import AgentWindowHistoryMessage


def compose_jarvis_user_message(
    user_message: str,
    *,
    context_block: str,
    conversation_history: list[AgentWindowHistoryMessage] | None = None,
    max_history_turns: int = 10,
) -> str:
    parts: list[str] = []

    if context_block.strip():
        parts.append(context_block.strip())

    history = conversation_history or []
    if history:
        trimmed = history[-max_history_turns * 2 :]
        lines = []
        for msg in trimmed:
            role = "Admin" if msg.role in ("user", "admin") else "Jarvis"
            content = (msg.content or "").strip()
            if content:
                lines.append(f"{role}: {content}")
        if lines:
            parts.append("[HISTORIQUE RÉCENT]\n" + "\n".join(lines) + "\n[FIN HISTORIQUE]")

    parts.append(f"Question admin : {(user_message or '').strip()}")
    return "\n\n".join(parts)
