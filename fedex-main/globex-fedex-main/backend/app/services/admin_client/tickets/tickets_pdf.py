"""Export PDF tickets admin — génération directe."""

from __future__ import annotations

from typing import Any

from app.services.client_phase3.pdf_body_composer import strip_markdown_for_pdf
from app.services.client_phase3.pdf_text import append_pdf_ready_note, build_text_pdf_download


def _fmt_dt(value: Any) -> str:
    if not value:
        return "—"
    return str(value)[:19]


def _lines_tickets_list(tickets: list[dict[str, Any]], *, lang: str = "fr") -> str:
    if not tickets:
        return (
            "Aucun ticket à exporter."
            if lang == "fr"
            else "No tickets to export."
        )
    lines = ["Tickets support" if lang == "fr" else "Support tickets", ""]
    for t in tickets:
        lines.append(
            f"#{t.get('id')} — {t.get('ticket_number', '—')} — {t.get('subject', '—')}\n"
            f"  Client : {t.get('user_email') or '—'} | Statut : {t.get('status', '—')} | "
            f"Priorité : {t.get('priority', '—')} | {_fmt_dt(t.get('updated_at'))}"
        )
    return "\n".join(lines)


def _lines_ticket_detail(ticket: dict[str, Any], *, lang: str = "fr") -> str:
    lines = [
        f"Ticket #{ticket.get('id')} — {ticket.get('ticket_number', '—')}",
        f"Sujet : {ticket.get('subject', '—')}",
        f"Client : {ticket.get('user_name', '—')} ({ticket.get('user_email', '—')})",
        f"Statut : {ticket.get('status', '—')} | Priorité : {ticket.get('priority', '—')}",
        "",
        "Message initial :" if lang == "fr" else "Initial message:",
        (ticket.get("message") or "—")[:2000],
    ]
    messages = ticket.get("messages") or []
    if messages:
        lines.extend(["", "Conversation :" if lang == "fr" else "Thread:"])
        for row in messages[-20:]:
            created = _fmt_dt(row.get("created_at"))
            role = row.get("author_role", "—")
            body = (row.get("body") or "—")[:400]
            lines.append(f"{created} [{role}] {body}")
    return "\n".join(lines)


def build_tickets_pdf_export(
    admin_id: int,
    session_id: int,
    *,
    export_kind: str,
    processed: dict[str, Any],
    lang: str = "fr",
    status_filter: str | None = None,
) -> tuple[str, dict[str, Any] | None]:
    if export_kind == "detail":
        ticket = processed.get("ticket") or {}
        if not ticket:
            msg = (
                "Aucun ticket à exporter en PDF."
                if lang == "fr"
                else "No ticket to export as PDF."
            )
            return msg, None
        body = _lines_ticket_detail(ticket, lang=lang)
        title = f"Ticket {ticket.get('ticket_number') or ticket.get('id')}"
        filename_hint = f"ticket_{ticket.get('id', 'x')}"
    else:
        tickets = processed.get("tickets") or (processed.get("summary") or {}).get("tickets") or []
        if not tickets:
            msg = (
                "Aucun ticket ne correspond aux filtres — PDF non généré."
                if lang == "fr"
                else "No tickets match the filters — PDF not generated."
            )
            return msg, None
        body = _lines_tickets_list(tickets, lang=lang)
        suffix = f"_{status_filter}" if status_filter and status_filter != "all" else ""
        title = "Tickets support Globex"
        filename_hint = f"tickets{suffix}"

    pdf_body = strip_markdown_for_pdf(body)
    export_download = build_text_pdf_download(
        admin_id,
        pdf_body,
        title=title,
        session_id=session_id,
    )
    export_download["filename"] = f"{filename_hint}.pdf"
    note = (
        "Votre PDF tickets est prêt — utilisez le lien de téléchargement ci-dessous."
        if lang == "fr"
        else "Your tickets PDF is ready — use the download link below."
    )
    return append_pdf_ready_note(note), export_download
