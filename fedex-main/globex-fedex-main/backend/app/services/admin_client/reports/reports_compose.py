"""Réponses déterministes centre de rapports admin."""

from __future__ import annotations

from typing import Any

from app.services.admin_client.reports.reports_share_pending import build_share_pending_marker
from app.services.admin_client.reports.reports_types import ReportsPlan, ReportsProfile

_SOURCE_FOOTER_FR = "\n\n_Source : Centre de rapports Admin_"
_SOURCE_FOOTER_EN = "\n\n_Source: Admin Reports Center_"


def reports_source_footer(lang: str) -> str:
    return _SOURCE_FOOTER_EN if lang == "en" else _SOURCE_FOOTER_FR


def _format_status(status: str | None, lang: str) -> str:
    s = (status or "").strip().lower()
    if lang == "fr" and s in {"completed", "complete", "success", "done"}:
        return "complet"
    if lang == "en" and s in {"completed", "complet", "complete", "success", "done"}:
        return "completed"
    return status or "—"


def compose_reports_response(
    processed: dict[str, Any],
    plan: ReportsPlan,
    *,
    lang: str = "fr",
    share_result: dict[str, Any] | None = None,
    include_footer: bool = True,
) -> str:
    profile = plan.profile
    if share_result is not None:
        profile = ReportsProfile.SHARE_DONE

    if profile == ReportsProfile.PREVIEW:
        body = _compose_preview(processed, lang)
    elif profile == ReportsProfile.LIST:
        body = _compose_list(processed, lang)
    elif profile == ReportsProfile.DOWNLOAD:
        body = _compose_download(processed, lang)
    elif profile == ReportsProfile.SHARE_PROMPT:
        body = _compose_share_prompt(processed, lang)
    elif profile == ReportsProfile.SHARE_DONE:
        body = _compose_share_done(share_result or {}, lang)
    elif profile == ReportsProfile.CLARIFY:
        body = plan.clarification_question or (
            "Pouvez-vous préciser votre demande concernant les rapports ?"
            if lang == "fr"
            else "Could you clarify your reports request?"
        )
    elif profile == ReportsProfile.CONSULT:
        body = _compose_consult(processed, lang)
    else:
        body = _compose_list(processed, lang)

    footer = reports_source_footer(lang) if include_footer else ""
    return body + footer


def _compose_preview(processed: dict[str, Any], lang: str) -> str:
    run = processed.get("run") or {}
    summary = processed.get("preview_summary") or {}
    title = "**Report preview**" if lang == "en" else "**Aperçu du rapport**"
    lines = [
        title,
        "",
        f"**{run.get('name', '—')}** (#{run.get('id', '—')}) — {run.get('format', '—')}",
        f"{'Rows' if lang == 'en' else 'Lignes'} : **{summary.get('total_rows', 0)}**",
        "",
    ]
    cols = summary.get("columns") or []
    if cols:
        lines.append("| " + " | ".join(str(c) for c in cols) + " |")
        lines.append("| " + " | ".join("---" for _ in cols) + " |")
        for row in (summary.get("sample_rows") or [])[:8]:
            lines.append("| " + " | ".join(str(c) for c in row) + " |")
    else:
        lines.append("Aucune donnée tabulaire." if lang == "fr" else "No tabular data.")
    return "\n".join(lines)


def _filter_label(processed: dict[str, Any], lang: str) -> str:
    filters = processed.get("filters") or {}
    parts: list[str] = []
    if filters.get("fmt"):
        parts.append(f"format **{filters['fmt']}**")
    if filters.get("slug"):
        parts.append(f"type **{filters['slug']}**")
    if filters.get("search") and not filters.get("slug"):
        parts.append(f"recherche « {filters['search']} »")
    if not parts:
        return ""
    joined = ", ".join(parts)
    return ("Filtre : " if lang == "fr" else "Filter: ") + joined


def _compose_list(processed: dict[str, Any], lang: str) -> str:
    runs = processed.get("runs") or []
    catalog = processed.get("catalog") or []
    file_av = processed.get("file_available") or {}
    title = "**Recent exports**" if lang == "en" else "**Exports récents**"
    lines = [title]
    fl = _filter_label(processed, lang)
    if fl:
        lines.append(fl)
    lines.append("")

    if catalog:
        cat_title = "**Report catalog**" if lang == "en" else "**Catalogue des rapports**"
        lines.append(cat_title)
        for item in catalog[:12]:
            last_id = item.get("last_run_id")
            status = item.get("last_status") or "—"
            suffix = f" — dernier run **#{last_id}**" if last_id else ""
            if lang == "en":
                suffix = f" — last run **#{last_id}**" if last_id else ""
            lines.append(
                f"- **{item.get('name', '—')}** ({item.get('slug')}) — "
                f"{item.get('default_format', '—')} — {status}{suffix}"
            )
        lines.append("")

    if not runs:
        lines.append("No exports found." if lang == "en" else "Aucun export trouvé.")
        return "\n".join(lines)

    run_title = "**Generated exports**" if lang == "en" else "**Exports générés**"
    lines.append(run_title)
    for r in runs:
        rid = int(r.get("id") or 0)
        on_disk = file_av.get(rid, False)
        if lang == "en":
            file_note = "file on disk" if on_disk else "file missing — regenerate"
        else:
            file_note = "fichier disponible" if on_disk else "fichier absent — régénérez"
        lines.append(
            f"- **#{r.get('id')}** {r.get('name')} ({r.get('format')}) — "
            f"{_format_status(r.get('status'), lang)} — {r.get('row_count', 0)} lignes — {file_note}"
        )
    return "\n".join(lines)


def _compose_consult(processed: dict[str, Any], lang: str) -> str:
    run = processed.get("run") or {}
    file_av = processed.get("file_available") or {}
    rid = int(run.get("id") or 0)
    on_disk = file_av.get(rid, False)
    title = "**Report details**" if lang == "en" else "**Fiche du rapport**"
    lines = [
        title,
        "",
        f"**{run.get('name', '—')}** (#{run.get('id', '—')})",
        f"{'Type' if lang == 'en' else 'Type'} : {run.get('slug', '—')}",
        f"{'Format' if lang == 'en' else 'Format'} : **{run.get('format', '—')}**",
        f"{'Status' if lang == 'en' else 'Statut'} : {_format_status(run.get('status'), lang)}",
        f"{'Rows' if lang == 'en' else 'Lignes'} : **{run.get('row_count', 0)}**",
        f"{'Period' if lang == 'en' else 'Période'} : {run.get('period_label') or '—'}",
        f"{'Category' if lang == 'en' else 'Catégorie'} : {run.get('category') or '—'}",
    ]
    if run.get("generated_by_name"):
        label = "Generated by" if lang == "en" else "Généré par"
        lines.append(f"{label} : {run.get('generated_by_name')}")
    if on_disk:
        lines.append(
            "Le fichier est disponible — demandez un aperçu tabulaire ou un téléchargement."
            if lang == "fr"
            else "File is available — ask for a tabular preview or download."
        )
    else:
        lines.append(
            "Le fichier n'est plus sur le disque. Régénérez l'export depuis le Centre de rapports, "
            "puis relancez la prévisualisation ou le téléchargement."
            if lang == "fr"
            else "File is not on disk. Regenerate from the Reports Center, then preview or download again."
        )
    preview_summary = processed.get("preview_summary")
    if preview_summary and preview_summary.get("columns"):
        lines.extend(["", "**Aperçu (extrait)**" if lang == "fr" else "**Preview (sample)**", ""])
        cols = preview_summary.get("columns") or []
        lines.append("| " + " | ".join(str(c) for c in cols) + " |")
        lines.append("| " + " | ".join("---" for _ in cols) + " |")
        for row in (preview_summary.get("sample_rows") or [])[:5]:
            lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def _compose_download(processed: dict[str, Any], lang: str) -> str:
    run = processed.get("run") or {}
    title = "**Download ready**" if lang == "en" else "**Téléchargement prêt**"
    return "\n".join(
        [
            title,
            "",
            f"**{run.get('name', '—')}** (#{run.get('id')}) — format **{run.get('format', '—')}**",
            f"{'Rows' if lang == 'en' else 'Lignes'} : **{run.get('row_count', 0)}**",
            "",
            "Utilisez le bouton de téléchargement ci-dessous."
            if lang == "fr"
            else "Use the download button below.",
        ]
    )


def _compose_share_prompt(processed: dict[str, Any], lang: str) -> str:
    run = processed.get("run") or {}
    recipients = processed.get("recipients") or []
    emails = [str(r.get("email")) for r in recipients if r.get("email")]
    inactive = [r for r in recipients if r.get("inactive")]

    if lang == "en":
        lines = [
            "**Confirm report sharing**",
            "",
            f"Report: **{run.get('name', '—')}** (#{run.get('id')})",
        ]
        if not emails:
            lines.append("No active recipient found in the database.")
        else:
            lines.append("Recipients: " + ", ".join(f"**{e}**" for e in emails))
        if inactive:
            lines.append("Some users are inactive and will be skipped.")
        lines.extend(["", "Reply **yes** or **no** to confirm sending."])
    else:
        lines = [
            "**Confirmation de partage**",
            "",
            f"Rapport : **{run.get('name', '—')}** (#{run.get('id')})",
        ]
        if not emails:
            lines.append("Aucun destinataire actif trouvé en base.")
        else:
            lines.append("Destinataires : " + ", ".join(f"**{e}**" for e in emails))
        if inactive:
            lines.append("Certains utilisateurs sont inactifs et seront ignorés.")
        lines.extend(["", "Répondez **oui** ou **non** pour confirmer l'envoi."])

    if emails and run.get("id"):
        lines.append(build_share_pending_marker(int(run["id"]), emails))
    return "\n".join(lines)


def _compose_share_done(result: dict[str, Any], lang: str) -> str:
    sent = result.get("sent_to") or []
    failures = result.get("failures") or []
    skipped = result.get("skipped_unknown_or_inactive") or []
    if lang == "en":
        lines = ["**Report sent**", "", f"Report: **{result.get('run_name', '—')}**"]
    else:
        lines = ["**Rapport envoyé**", "", f"Rapport : **{result.get('run_name', '—')}**"]
    if sent:
        lines.append(("Sent to: " if lang == "en" else "Envoyé à : ") + ", ".join(sent))
    if failures:
        lines.append(("Failures: " if lang == "en" else "Échecs : ") + ", ".join(failures))
    if skipped:
        lines.append(("Skipped: " if lang == "en" else "Ignorés : ") + ", ".join(skipped))
    if not result.get("smtp_ok"):
        lines.append("SMTP not configured." if lang == "en" else "SMTP non configuré.")
    return "\n".join(lines)
