"""Repli factuel résumé notifications — sans LLM."""

from __future__ import annotations

from app.schemas.user_notifications import UserNotificationRead


def build_notifications_transcript(items: list[UserNotificationRead]) -> str:
    lines: list[str] = []
    for item in items:
        created = item.created_at.strftime("%Y-%m-%d %H:%M") if item.created_at else ""
        tn = item.related_tracking_number or ""
        tn_part = f" ({tn})" if tn else ""
        lines.append(f"[{created}] {item.type} · {item.title}{tn_part}")
        msg = (item.message or "").strip()
        if msg:
            lines.append(msg)
        lines.append("")
    return "\n".join(lines).strip()


def build_factual_notification_summary(
    items: list[UserNotificationRead],
    *,
    lang: str,
    filter_label: str = "",
) -> str:
    if not items:
        return ""

    tracking_nums: list[str] = []
    kinds: set[str] = set()
    unread = 0
    for item in items:
        kinds.add(item.type)
        if not item.is_read:
            unread += 1
        tn = (item.related_tracking_number or "").strip()
        if tn and tn not in tracking_nums:
            tracking_nums.append(tn)

    filter_part = f" ({filter_label})" if filter_label else ""
    if lang == "en":
        intro = f"The client had {len(items)} notification(s){filter_part}, {unread} unread."
        kind_part = f" Types mentioned: {', '.join(sorted(kinds))}."
        tn_part = f" Tracking numbers cited: {', '.join(tracking_nums[:5])}." if tracking_nums else ""
        return intro + kind_part + tn_part

    intro = f"Le client avait {len(items)} notification(s){filter_part}, dont {unread} non lue(s)."
    kind_part = f" Types concernés : {', '.join(sorted(kinds))}."
    tn_part = (
        f" Numéros de suivi mentionnés : {', '.join(tracking_nums[:5])}."
        if tracking_nums
        else ""
    )
    sentences = [intro]
    for item in items[:5]:
        status = "non lue" if not item.is_read else "lue"
        sentences.append(f"L'alerte « {item.title} » était {status}.")
    if tracking_nums:
        sentences.append(f"Les numéros {', '.join(tracking_nums[:5])} ont été mentionnés.")
    return " ".join(sentences[:6])
