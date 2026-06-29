"""Résumé factuel notifications plateforme admin — sans LLM ni statut colis inventé."""

from __future__ import annotations

from app.schemas.user_notifications import UserNotificationRead


def _truncate(text: str, max_len: int = 160) -> str:
    msg = (text or "").strip()
    if len(msg) <= max_len:
        return msg
    return msg[: max_len - 3] + "..."


def generate_admin_platform_notifications_summary(
    items: list[UserNotificationRead],
    *,
    lang: str,
    filter_label: str = "",
) -> str:
    """Remplace le résumé LLM client par une synthèse factuelle alignée cloche admin."""
    if not items:
        if lang == "en":
            return "No platform notifications match your request."
        return "Aucune notification plateforme ne correspond à votre demande."

    unread = sum(1 for item in items if not item.is_read)
    filter_part = f" ({filter_label})" if filter_label else ""

    if lang == "en":
        header = (
            f"Platform summary{filter_part}: {len(items)} notification(s), "
            f"{unread} unread."
        )
    else:
        header = (
            f"Synthèse plateforme{filter_part} : {len(items)} notification(s), "
            f"dont {unread} non lue(s)."
        )

    lines = [header, ""]
    for index, item in enumerate(items[:10], start=1):
        status = "unread" if not item.is_read else "read"
        if lang != "en":
            status = "non lue" if not item.is_read else "lue"
        msg = _truncate(item.message or "")
        lines.append(f"{index}. [{status}] **{item.title}**")
        if msg:
            lines.append(f"   {msg}")
    return "\n".join(lines)
