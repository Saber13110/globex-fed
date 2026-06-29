"""Export PDF utilisateurs admin — génération directe (pas centre rapports)."""

from __future__ import annotations

from typing import Any

from app.services.client_phase3.pdf_body_composer import strip_markdown_for_pdf
from app.services.client_phase3.pdf_text import append_pdf_ready_note, build_text_pdf_download


def _fmt_dt(value: Any) -> str:
    if not value:
        return "—"
    return str(value)[:19]


def _lines_users_list(
    users: list[dict[str, Any]],
    *,
    show_activity: bool = False,
    lang: str = "fr",
) -> str:
    if not users:
        empty = "Aucun utilisateur à exporter." if lang == "fr" else "No users to export."
        return empty

    lines = ["Liste des utilisateurs" if lang == "fr" else "User list", ""]
    for u in users:
        if show_activity:
            online = ("Oui" if lang == "fr" else "Yes") if u.get("is_online") else ("Non" if lang == "fr" else "No")
            lines.append(
                f"#{u.get('id')} — {u.get('full_name', '—')} — {u.get('email', '—')}\n"
                f"  Dernière activité : {_fmt_dt(u.get('last_activity_at'))} | "
                f"En ligne : {online} | Machine : {u.get('last_location') or '—'}"
            )
        else:
            lines.append(
                f"#{u.get('id')} — {u.get('full_name', '—')} — {u.get('email', '—')} "
                f"({u.get('role', '—')} / {u.get('status', '—')})"
            )
    return "\n".join(lines)


def _lines_user_logs(user: dict[str, Any], logs: list[dict[str, Any]]) -> str:
    lines = [f"Logs utilisateur #{user.get('id')} — {user.get('email', '')}", ""]
    for row in logs[:80]:
        created = str(row.get("created_at", ""))[:19]
        lines.append(
            f"{created} | {row.get('level', '—')} | {row.get('action', '—')} | "
            f"{(row.get('message') or '')[:200]}"
        )
    return "\n".join(lines)


def _list_pdf_meta(
    *,
    status_filter: str | None,
    list_variant: str | None,
    lang: str,
) -> tuple[str, str]:
    if status_filter == "suspended":
        return (
            "Utilisateurs suspendus" if lang == "fr" else "Suspended users",
            "users_suspended",
        )
    if list_variant == "ever_suspended":
        return (
            "Utilisateurs suspendus au moins une fois" if lang == "fr" else "Users ever suspended",
            "users_ever_suspended",
        )
    if list_variant == "activity":
        return (
            "Activité utilisateurs" if lang == "fr" else "User activity",
            "users_activity",
        )
    return (
        "Liste utilisateurs" if lang == "fr" else "User list",
        "users_list",
    )


def build_users_pdf_export(
    admin_id: int,
    session_id: int,
    *,
    export_kind: str,
    processed: dict[str, Any],
    lang: str = "fr",
    status_filter: str | None = None,
    list_variant: str | None = None,
    sort_by: str | None = None,
) -> tuple[str, dict[str, Any] | None]:
    if export_kind == "logs":
        user = processed.get("user") or {}
        logs = processed.get("logs") or []
        if not logs and not user:
            msg = (
                "Aucun log à exporter en PDF pour cet utilisateur."
                if lang == "fr"
                else "No logs to export as PDF for this user."
            )
            return msg, None
        body = _lines_user_logs(user, logs)
        title = f"Logs {user.get('email', 'user')}"
        filename_hint = f"logs_user_{user.get('id', 'x')}"
    else:
        users = processed.get("users") or []
        if not users:
            msg = (
                "Aucun utilisateur ne correspond aux filtres — PDF non généré."
                if lang == "fr"
                else "No users match the filters — PDF not generated."
            )
            return msg, None
        show_activity = list_variant == "activity" or sort_by in {"last_activity", "online"}
        body = _lines_users_list(users, show_activity=show_activity, lang=lang)
        title, filename_hint = _list_pdf_meta(
            status_filter=status_filter,
            list_variant=list_variant,
            lang=lang,
        )

    pdf_body = strip_markdown_for_pdf(body)
    export_download = build_text_pdf_download(
        admin_id,
        pdf_body,
        title=title,
        session_id=session_id,
    )
    export_download["filename"] = f"{filename_hint}.pdf"
    note = (
        "Votre PDF utilisateurs est prêt — utilisez le lien de téléchargement ci-dessous."
        if lang == "fr"
        else "Your users PDF is ready — use the download link below."
    )
    return append_pdf_ready_note(note), export_download
