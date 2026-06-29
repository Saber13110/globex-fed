"""Réponses déterministes tickets support admin."""

from __future__ import annotations

from typing import Any

from app.services.admin_client.tickets.tickets_pending import (
    TICKETS_CONFIRM_MARKER_EN,
    TICKETS_CONFIRM_MARKER_FR,
    build_tickets_pending_marker,
)
from app.services.admin_client.tickets.tickets_types import TicketsPlan, TicketsProfile, TicketsTaskType


def compose_tickets_response(
    processed: dict[str, Any],
    plan: TicketsPlan,
    *,
    lang: str = "fr",
    error_code: str | None = None,
    action_result: dict[str, Any] | None = None,
) -> str:
    if error_code:
        return _error_text(error_code, lang)
    if plan.profile == TicketsProfile.LIST:
        return _compose_list(processed, lang)
    if plan.profile == TicketsProfile.SUMMARY:
        return _compose_summary(processed, lang)
    if plan.profile == TicketsProfile.DETAIL:
        return _compose_detail(processed, lang)
    if plan.profile == TicketsProfile.DETAILS_BATCH:
        return _compose_details_batch(processed, lang)
    if plan.profile == TicketsProfile.CONFIRM:
        return _compose_confirm(processed, plan, lang)
    if plan.profile == TicketsProfile.DONE:
        return _compose_done(processed, plan, action_result or {}, lang)
    if plan.profile == TicketsProfile.CLARIFY:
        return plan.clarification_question or default_clarify(lang)
    if plan.profile == TicketsProfile.ERROR:
        return f"**{'Erreur' if lang == 'fr' else 'Error'}** — {processed.get('message', '—')}"
    return _compose_list(processed, lang)


def default_clarify(lang: str) -> str:
    if lang == "en":
        return "Could you clarify your support tickets request?"
    return "Pouvez-vous préciser votre demande concernant les tickets support ?"


def _error_text(code: str, lang: str) -> str:
    catalog_fr = {
        "ticket_not_found": "Ticket introuvable.",
        "fetch_failed": "Impossible de récupérer les tickets en temps réel.",
        "ticket_closed": "Ce ticket est fermé — réponse impossible.",
        "empty_reply": "Le message de réponse est vide.",
        "reply_failed": "Échec de l'envoi de la réponse.",
        "invalid_status": "Statut ticket invalide.",
    }
    catalog_en = {
        "ticket_not_found": "Ticket not found.",
        "fetch_failed": "Could not fetch live ticket data.",
        "ticket_closed": "This ticket is closed — cannot reply.",
        "empty_reply": "Reply message is empty.",
        "reply_failed": "Failed to send the reply.",
        "invalid_status": "Invalid ticket status.",
    }
    catalog = catalog_en if lang == "en" else catalog_fr
    label = "Erreur" if lang == "fr" else "Error"
    return f"**{label}** — {catalog.get(code, code)}"


def _filter_bits(filters: dict[str, Any], lang: str) -> list[str]:
    bits: list[str] = []
    if filters.get("status"):
        bits.append(f"statut={filters['status']}" if lang == "fr" else f"status={filters['status']}")
    if filters.get("priority"):
        bits.append(f"priorité={filters['priority']}" if lang == "fr" else f"priority={filters['priority']}")
    if filters.get("category"):
        bits.append(f"catégorie={filters['category']}" if lang == "fr" else f"category={filters['category']}")
    if filters.get("search"):
        bits.append(f"recherche={filters['search']}")
    return bits


def _compose_list(processed: dict[str, Any], lang: str) -> str:
    tickets = processed.get("tickets") or []
    title = "**Liste des tickets support**" if lang == "fr" else "**Support ticket list**"
    filters = processed.get("filters") or {}
    filter_bits = _filter_bits(filters, lang)
    header = title + (f" ({', '.join(filter_bits)})" if filter_bits else "")

    if not tickets:
        empty = (
            "Aucun ticket ne correspond aux filtres."
            if lang == "fr"
            else "No tickets match the filters."
        )
        return f"{header}\n\n{empty}"

    lines = [
        header,
        "",
        f"{'Affichés' if lang == 'fr' else 'Shown'} : **{len(tickets)}**",
        "",
        "| # | TKT | Sujet | Client | Statut | Priorité |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for t in tickets:
        client = t.get("user_email") or t.get("user_name") or "—"
        subject = (t.get("subject") or "—").replace("|", "\\|")[:60]
        lines.append(
            f"| {t.get('id')} | {t.get('ticket_number', '—')} | {subject} | "
            f"{client} | {t.get('status', '—')} | {t.get('priority', '—')} |"
        )
    hint = (
        "\n\n_Indice : précisez #id, TKT-… ou « le N » pour le détail._"
        if lang == "fr"
        else "\n\n_Tip: use #id, TKT-…, or « row N » for details._"
    )
    return "\n".join(lines) + hint


def _compose_summary(processed: dict[str, Any], lang: str) -> str:
    summary = processed.get("summary") or {}
    tickets = summary.get("tickets") or processed.get("tickets") or []
    title = "**Résumé des tickets support**" if lang == "fr" else "**Support tickets summary**"
    filters = processed.get("filters") or {}
    filter_bits = _filter_bits(filters, lang)
    header = title + (f" ({', '.join(filter_bits)})" if filter_bits else "")

    total = summary.get("total", len(tickets))
    by_status = summary.get("by_status") or {}
    by_priority = summary.get("by_priority") or {}

    if total == 0:
        empty = "Aucun ticket pour ces critères." if lang == "fr" else "No tickets for these criteria."
        return f"{header}\n\n{empty}"

    lines = [
        header,
        "",
        f"**Total** : {total}",
    ]
    if by_status:
        status_line = ", ".join(f"{k}: {v}" for k, v in sorted(by_status.items()))
        lines.append(
            f"**{'Par statut' if lang == 'fr' else 'By status'}** : {status_line}"
        )
    if by_priority:
        prio_line = ", ".join(f"{k}: {v}" for k, v in sorted(by_priority.items()))
        lines.append(
            f"**{'Par priorité' if lang == 'fr' else 'By priority'}** : {prio_line}"
        )
    lines.append("")
    lines.append("**Tickets** :" if lang == "fr" else "**Tickets**:")
    for t in tickets[:12]:
        lines.append(
            f"- **#{t.get('id')}** [{t.get('status')}] {t.get('subject', '—')[:80]} "
            f"— {t.get('user_email') or '—'}"
        )
    if total > 12:
        lines.append(
            f"\n_… {total - 12} ticket(s) supplémentaire(s)._"
            if lang == "fr"
            else f"\n_… {total - 12} more ticket(s)._"
        )
    return "\n".join(lines)


def _compose_details_batch(processed: dict[str, Any], lang: str) -> str:
    details = processed.get("details") or []
    filters = processed.get("filters") or {}
    filter_bits = _filter_bits(filters, lang)
    title = (
        "**Détails des tickets support**"
        if lang == "fr"
        else "**Support ticket details**"
    )
    header = title + (f" ({', '.join(filter_bits)})" if filter_bits else "")

    if not details:
        empty = (
            "Aucun ticket ne correspond aux filtres."
            if lang == "fr"
            else "No tickets match the filters."
        )
        return f"{header}\n\n{empty}"

    blocks: list[str] = [header, ""]
    for t in details:
        blocks.append(f"### #{t.get('id')} — {t.get('subject', '—')}")
        blocks.append(
            f"Client : {t.get('user_name', '—')} ({t.get('user_email', '—')}) | "
            f"Statut : **{t.get('status', '—')}** | Priorité : {t.get('priority', '—')}"
        )
        blocks.append("")
        blocks.append((t.get("message") or "—")[:400])
        messages = t.get("messages") or []
        if messages:
            last = messages[-1]
            body = (last.get("body") or "—")[:200].replace("\n", " ")
            blocks.append(
                f"_Dernier message ({last.get('author_role', '—')}) : {body}_"
            )
        blocks.append("")
    return "\n".join(blocks).strip()


def _compose_detail(processed: dict[str, Any], lang: str) -> str:
    t = processed.get("ticket") or {}
    title = "**Fiche ticket**" if lang == "fr" else "**Ticket detail**"
    lines = [
        title,
        "",
        f"**#{t.get('id')}** — {t.get('ticket_number', '—')}",
        f"**{t.get('subject', '—')}**",
        f"Client : {t.get('user_name', '—')} ({t.get('user_email', '—')})",
        f"Statut : **{t.get('status', '—')}** | Priorité : **{t.get('priority', '—')}** | "
        f"Catégorie : {t.get('category', '—')}",
        "",
        f"**{'Message initial' if lang == 'fr' else 'Initial message'}** :",
        (t.get("message") or "—")[:500],
    ]
    messages = t.get("messages") or []
    if messages:
        lines.extend(["", f"**{'Conversation' if lang == 'fr' else 'Thread'}** :"])
        for row in messages[-15:]:
            created = str(row.get("created_at", ""))[:19]
            role = row.get("author_role", "—")
            name = row.get("author_name") or role
            body = (row.get("body") or "—").replace("\n", " ")[:300]
            lines.append(f"- **{created}** _{name}_ ({role}) : {body}")
    return "\n".join(lines)


def _action_label(task: TicketsTaskType, lang: str) -> str:
    labels_fr = {
        TicketsTaskType.ticket_reply: "envoyer une réponse au client",
        TicketsTaskType.ticket_resolve: "modifier le statut du ticket",
    }
    labels_en = {
        TicketsTaskType.ticket_reply: "send a reply to the client",
        TicketsTaskType.ticket_resolve: "update the ticket status",
    }
    catalog = labels_en if lang == "en" else labels_fr
    return catalog.get(task, task.value)


def _compose_confirm(processed: dict[str, Any], plan: TicketsPlan, lang: str) -> str:
    t = processed.get("ticket") or {}
    action = _action_label(plan.task_type, lang)
    lines = [
        f"**{'Confirmation requise' if lang == 'fr' else 'Confirmation required'}**",
        "",
        f"Vous demandez à **{action}** :" if lang == "fr" else f"You are about to **{action}**:",
        f"- **#{t.get('id')}** {t.get('ticket_number', '—')} — {t.get('subject', '—')}",
        f"- Client : {t.get('user_email', '—')} | Statut actuel : **{t.get('status', '—')}**",
    ]
    payload: dict[str, str] = {}
    action_key = "reply"
    if plan.task_type == TicketsTaskType.ticket_reply:
        body = (plan.reply_body or "").strip()
        lines.extend(["", f"**{'Message' if lang == 'fr' else 'Message'}** :", body[:1500]])
        payload["reply_body"] = body
    elif plan.task_type == TicketsTaskType.ticket_resolve:
        action_key = "resolve"
        target = plan.target_status or "resolved"
        label = "résolu" if target == "resolved" else "fermé"
        if lang == "en":
            label = "resolved" if target == "resolved" else "closed"
        lines.append(f"- Nouveau statut : **{label}** ({target})")
        payload["target_status"] = target

    if plan.notify_email:
        payload["notify_email"] = "true"

    marker_text = TICKETS_CONFIRM_MARKER_FR if lang == "fr" else TICKETS_CONFIRM_MARKER_EN
    lines.extend(["", marker_text + "."])
    pending = build_tickets_pending_marker(
        action_key,
        int(t.get("id") or plan.ticket_id or 0),
        payload,
    )
    return "\n".join(lines) + pending


def _compose_done(
    processed: dict[str, Any],
    plan: TicketsPlan,
    result: dict[str, Any],
    lang: str,
) -> str:
    t = processed.get("ticket") or {}
    subject = result.get("subject") or t.get("subject", "—")
    tid = result.get("ticket_id") or t.get("id", "—")
    if plan.task_type == TicketsTaskType.ticket_reply:
        msg = (
            f"Réponse envoyée sur le ticket **#{tid}** — {subject}."
            if lang == "fr"
            else f"Reply sent on ticket **#{tid}** — {subject}."
        )
    else:
        status = result.get("status") or plan.target_status
        msg = (
            f"Ticket **#{tid}** marqué **{status}**."
            if lang == "fr"
            else f"Ticket **#{tid}** marked **{status}**."
        )
    return f"**{'Action effectuée' if lang == 'fr' else 'Action completed'}**\n\n{msg}"
