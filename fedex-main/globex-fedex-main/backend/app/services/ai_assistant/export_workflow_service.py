"""Workflow export admin — preview → confirmation → génération fichier."""

from __future__ import annotations

import csv
import io
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.tracking_request import TrackingRequest
from app.models.user import User, UserRole
from app.services.admin_logs_export_service import fetch_activity_logs
from app.services.copilot_export_service import build_export_download_spec

logger = logging.getLogger(__name__)

# ── Intent patterns ──────────────────────────────────────────────────────────

_MODULE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(logs?|journaux|activit[eé])\b", re.I), "logs"),
    (re.compile(r"\b(tracking|colis|exp[eé]ditions?|shipments?)\b", re.I), "tracking"),
    (re.compile(r"\b(utilisateurs?|users?|comptes?)\b", re.I), "users"),
    (re.compile(r"\b(notifications?)\b", re.I), "notifications"),
    (re.compile(r"\b(tickets?|support)\b", re.I), "tickets"),
    (re.compile(r"\b(s[eé]curit[eé]|security|incidents?)\b", re.I), "security"),
    (re.compile(r"\b(missions?|agent\s+missions?)\b", re.I), "missions"),
    (re.compile(r"\b(rapport|report|plateforme|platform|executive|kpi)\b", re.I), "platform_report"),
]

_EXPORT_VERB = re.compile(
    r"\b(export|exporte|exporter|g[eé]n[eè]re|generer|t[eé]l[eé]charge|download|produce)\b",
    re.I,
)

_FORMAT_MAP: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(excel|xlsx)\b", re.I), "xlsx"),
    (re.compile(r"\bcsv\b", re.I), "csv"),
    (re.compile(r"\b(word|docx|doc)\b", re.I), "docx"),
    (re.compile(r"\bjson\b", re.I), "json"),
    (re.compile(r"\bpdf\b", re.I), "pdf"),
]

_EMPLOYEE_ALLOWED = frozenset({"logs", "tracking", "notifications"})


@dataclass
class ExportIntent:
    module: str
    fmt: str = "pdf"
    hours: int = 24
    limit: int = 50
    period: str | None = None  # weekly | monthly
    intent_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])


@dataclass
class ExportPreview:
    intent_id: str
    module: str
    fmt: str
    records: int
    period_label: str
    estimated_size_kb: int
    filename: str
    hours: int
    limit: int
    period: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "module": self.module,
            "format": self.fmt,
            "records": self.records,
            "period": self.period_label,
            "estimated_size_kb": self.estimated_size_kb,
            "filename": self.filename,
            "hours": self.hours,
            "limit": self.limit,
            "period_type": self.period,
        }


def _parse_hours(message: str) -> int:
    m = re.search(r"\b(\d{1,3})\s*(?:derni[eè]res?|last)?\s*(?:heures?|hours?|h)\b", message, re.I)
    if m:
        return min(int(m.group(1)), 168)
    if re.search(r"\b(semaine|weekly|week|7\s*jours?)\b", message, re.I):
        return 168
    if re.search(r"\b(mois|monthly|30\s*jours?)\b", message, re.I):
        return 720
    if re.search(r"\b24\s*h|\b24h\b", message, re.I):
        return 24
    return 24


def _parse_limit(message: str) -> int:
    m = re.search(r"\b(\d{1,3})\s*(?:derniers?|last|premiers?|top)\b", message, re.I)
    if m:
        return min(int(m.group(1)), 500)
    m = re.search(r"\blimit[eé]?\s*[àa]?\s*(\d+)\b", message, re.I)
    if m:
        return min(int(m.group(1)), 500)
    return 50


def _detect_format(message: str) -> str:
    for pattern, fmt in _FORMAT_MAP:
        if pattern.search(message):
            return fmt
    return "pdf"


def _detect_module(message: str) -> str | None:
    text = message or ""
    if re.search(r"\b(rapport|report).{0,30}(plateforme|platform|global|executive|ia|ai)\b", text, re.I):
        return "platform_report"
    if re.search(r"\b(r[eé]sum[eé]|summary).{0,20}(semaine|weekly|week)\b", text, re.I):
        return "weekly_summary"
    if re.search(r"\b(r[eé]sum[eé]|summary).{0,20}(mois|monthly|month)\b", text, re.I):
        return "monthly_summary"
    for pattern, module in _MODULE_PATTERNS:
        if pattern.search(text):
            return module
    return None


def detect_export_intent(message: str) -> ExportIntent | None:
    """Détecte une demande d'export admin."""
    text = (message or "").strip()
    if not text or not _EXPORT_VERB.search(text):
        return None
    module = _detect_module(text)
    if not module:
        return None
    fmt = _detect_format(text)
    hours = _parse_hours(text)
    limit = _parse_limit(text)
    period = None
    if module == "weekly_summary":
        hours = 168
        period = "weekly"
        module = "platform_report"
    elif module == "monthly_summary":
        hours = 720
        period = "monthly"
        module = "platform_report"
    return ExportIntent(module=module, fmt=fmt, hours=hours, limit=limit, period=period)


def _estimate_size_kb(records: int, fmt: str) -> int:
    per_row = {"pdf": 0.9, "xlsx": 0.25, "csv": 0.12, "json": 0.18, "docx": 0.45}
    return max(1, int(records * per_row.get(fmt, 0.5)) + 5)


def _period_label(hours: int, period: str | None, lang: str) -> str:
    if period == "weekly":
        return "7 derniers jours" if lang == "fr" else "Last 7 days"
    if period == "monthly":
        return "30 derniers jours" if lang == "fr" else "Last 30 days"
    if lang == "en":
        return f"Last {hours} hours"
    return f"{hours} dernières heures"


def _default_filename(module: str, fmt: str, hours: int, records: int) -> str:
    ext = fmt if fmt != "xlsx" else "xlsx"
    ts = datetime.now(timezone.utc).strftime("%Y%m%d")
    if module == "platform_report":
        return f"platform-report-{ts}.{ext}"
    return f"{module}-{hours}h-{records}rec-{ts}.{ext}"


def _count_records(db: Session, admin: User, intent: ExportIntent) -> int:
    mod = intent.module
    if mod == "logs":
        since = datetime.now(timezone.utc) - timedelta(hours=intent.hours)
        from app.models.activity_log import ActivityLog

        return db.scalar(
            select(func.count()).select_from(ActivityLog).where(ActivityLog.created_at >= since)
        ) or 0
    if mod == "tracking":
        return db.scalar(select(func.count()).select_from(TrackingRequest)) or 0
    if mod == "users":
        return db.scalar(select(func.count()).select_from(User)) or 0
    if mod == "notifications":
        from app.models.platform_notification import PlatformNotification

        return db.scalar(select(func.count()).select_from(PlatformNotification)) or 0
    if mod == "tickets":
        from app.models.support_ticket import SupportTicket

        return db.scalar(
            select(func.count()).select_from(SupportTicket).where(SupportTicket.status == "open")
        ) or 0
    if mod == "security":
        from app.models.security_incident import SecurityIncident

        return db.scalar(
            select(func.count()).select_from(SecurityIncident).where(SecurityIncident.status == "open")
        ) or 0
    if mod == "platform_report":
        return 6  # sections KPI
    return intent.limit


def check_export_permission(user: User, module: str) -> tuple[bool, str | None]:
    role = (user.role or "admin").lower()
    if role == UserRole.admin.value:
        return True, None
    if role == UserRole.employe.value and module in _EMPLOYEE_ALLOWED:
        return True, None
    if role == UserRole.employe.value:
        return False, "Export non autorisé pour votre rôle sur ce module."
    return True, None


def prepare_export_preview(
    db: Session,
    admin: User,
    intent: ExportIntent,
    *,
    lang: str = "fr",
) -> tuple[ExportPreview | None, str | None]:
    """Prépare l'aperçu export — comptage + estimation."""
    allowed, err = check_export_permission(admin, intent.module)
    if not allowed:
        return None, err

    records = _count_records(db, admin, intent)
    records = min(records, 5000)
    size_kb = _estimate_size_kb(records, intent.fmt)
    filename = _default_filename(intent.module, intent.fmt, intent.hours, records)
    period_label = _period_label(intent.hours, intent.period, lang)

    preview = ExportPreview(
        intent_id=intent.intent_id,
        module=intent.module,
        fmt=intent.fmt,
        records=records,
        period_label=period_label,
        estimated_size_kb=size_kb,
        filename=filename,
        hours=intent.hours,
        limit=intent.limit,
        period=intent.period,
    )
    return preview, None


def format_preview_reply(preview: ExportPreview, *, lang: str) -> str:
    """Message markdown de preview pour l'admin."""
    mod_labels_fr = {
        "logs": "Journaux d'activité",
        "tracking": "Opérations tracking",
        "users": "Utilisateurs",
        "notifications": "Notifications",
        "tickets": "Tickets support",
        "security": "Rapport sécurité",
        "platform_report": "Rapport plateforme IA",
        "missions": "Missions agent",
    }
    mod_labels_en = {
        "logs": "Activity logs",
        "tracking": "Tracking operations",
        "users": "Users",
        "notifications": "Notifications",
        "tickets": "Support tickets",
        "security": "Security report",
        "platform_report": "AI Platform report",
        "missions": "Agent missions",
    }
    labels = mod_labels_en if lang == "en" else mod_labels_fr
    title = labels.get(preview.module, preview.module)

    if lang == "en":
        return (
            f"## Export ready — {title}\n\n"
            f"| Field | Value |\n|-------|-------|\n"
            f"| **Records** | {preview.records:,} |\n"
            f"| **Period** | {preview.period_label} |\n"
            f"| **Format** | {preview.fmt.upper()} |\n"
            f"| **Est. size** | ~{preview.estimated_size_kb} KB |\n"
            f"| **File** | `{preview.filename}` |\n\n"
            f"Click **Confirm** to generate the file, or **Cancel** to abort."
        )
    return (
        f"## Export prêt — {title}\n\n"
        f"| Champ | Valeur |\n|-------|--------|\n"
        f"| **Enregistrements** | {preview.records:,} |\n"
        f"| **Période** | {preview.period_label} |\n"
        f"| **Format** | {preview.fmt.upper()} |\n"
        f"| **Taille estimée** | ~{preview.estimated_size_kb} Ko |\n"
        f"| **Fichier** | `{preview.filename}` |\n\n"
        f"Cliquez sur **Confirmer** pour générer le fichier, ou **Annuler** pour abandonner."
    )


def build_suggested_action(preview: ExportPreview) -> dict[str, Any]:
    return {
        "type": "export",
        "intent_id": preview.intent_id,
        "module": preview.module,
        "format": preview.fmt,
        "hours": preview.hours,
        "limit": preview.limit,
        "filename": preview.filename,
        "period": preview.period,
    }


def build_download_url(spec: dict[str, Any]) -> str:
    """URL relative pour téléchargement frontend."""
    preset = spec.get("preset", "admin_logs")
    fmt = spec.get("format", "pdf")
    hours = spec.get("hours", 24)
    limit = spec.get("limit", 50)
    export_token = spec.get("export_token")
    if export_token:
        return (
            f"/admin/ai-assistant/export/context.pdf"
            f"?export_token={export_token}&preset={preset}&limit={limit}"
        )
    if preset == "admin_logs":
        if fmt == "xlsx":
            return f"/admin/ai-assistant/export/activity-logs.xlsx?hours={hours}"
        if fmt == "csv":
            return f"/admin/ai-assistant/export/activity-logs.csv?hours={hours}"
        return f"/admin/ai-assistant/export/activity-logs.pdf?hours={hours}"
    if preset == "admin_platform_report":
        return f"/admin/ai-assistant/export/platform-report.pdf?hours={hours}"
    mod = spec.get("module") or preset.replace("admin_", "")
    return f"/admin/ai-assistant/export/context.pdf?preset=admin_{mod}&limit={limit}&hours={hours}"


def execute_export(
    db: Session,
    admin: User,
    action: dict[str, Any],
) -> dict[str, Any]:
    """Exécute l'export après confirmation — retourne success + download spec."""
    module = (action.get("module") or "logs").lower()
    fmt = (action.get("format") or "pdf").lower()
    hours = min(max(int(action.get("hours") or 24), 1), 720)
    limit = min(max(int(action.get("limit") or 50), 1), 500)
    filename = action.get("filename") or _default_filename(module, fmt, hours, 0)

    allowed, err = check_export_permission(admin, module)
    if not allowed:
        return {"success": False, "error": err}

    from app.services.gpt.tool_handlers import HANDLERS
    from app.services.gpt.tool_types import ToolExecutionContext

    ctx = ToolExecutionContext(
        db=db,
        user_id=admin.id,
        user_role=(admin.role or "admin").lower(),
        gpt_slug="fedex-admin-ops",
        actor_admin_id=admin.id,
        ui_language="fr",
        analysis_mode=False,
    )

    records = 0
    export_spec: dict[str, Any] = {}

    if module == "logs":
        tool = "export_activity_logs_excel" if fmt == "xlsx" else "export_activity_logs_pdf"
        if fmt == "csv":
            logs = fetch_activity_logs(db, hours=hours, limit=500)
            records = len(logs)
            export_spec = build_export_download_spec(
                preset="admin_logs", filename=filename, fmt="csv", hours=hours,
            )
        elif tool in HANDLERS:
            result = HANDLERS[tool](ctx, {"hours": hours})
            if not result.success:
                return {"success": False, "error": result.error or "Export échoué."}
            records = result.data.get("entries", 0)
            export_spec = result.data.get("export_download") or build_export_download_spec(
                preset="admin_logs", filename=filename, fmt=fmt, hours=hours,
            )
        else:
            return {"success": False, "error": "Outil export logs indisponible."}

    elif module == "platform_report":
        records = _generate_platform_report(db, admin, hours=hours)
        export_spec = build_export_download_spec(
            preset="admin_platform_report", filename=filename, fmt="pdf", hours=hours,
        )

    else:
        preset_map = {
            "tracking": "admin_tracking",
            "users": "admin_users",
            "notifications": "admin_notifications",
            "tickets": "admin_tickets",
            "security": "admin_security",
            "conversations": "admin_conversations",
            "missions": "admin_generic",
        }
        preset = preset_map.get(module, f"admin_{module}")
        export_spec = build_export_download_spec(
            preset=preset,
            filename=filename,
            fmt=fmt if fmt in {"pdf", "xlsx"} else "pdf",
            hours=hours,
            limit=limit,
            module=module,
        )
        records = _count_records(db, admin, ExportIntent(module=module, hours=hours, limit=limit))

    download_url = build_download_url(export_spec)
    logger.info("[Export] executed module=%s fmt=%s records=%s", module, fmt, records)

    return {
        "success": True,
        "file_name": export_spec.get("filename", filename),
        "download_url": download_url,
        "records": records,
        "export_download": export_spec,
        "export_status": "completed",
    }


def _generate_platform_report(db: Session, admin: User, *, hours: int) -> int:
    """Génère un rapport plateforme — retourne le nombre de sections."""
    from app.services.ai_assistant.composite_tools import run_composite_tool
    from app.services.gpt.tool_types import ToolExecutionContext

    ctx = ToolExecutionContext(
        db=db, user_id=admin.id, user_role="admin", gpt_slug="fedex-admin-ops",
        actor_admin_id=admin.id, ui_language="fr", analysis_mode=True,
    )
    run_composite_tool(ctx, "analyze_platform_health", {})
    return 6


def generate_logs_csv(db: Session, *, hours: int) -> tuple[bytes, str]:
    """Export CSV des logs."""
    logs = fetch_activity_logs(db, hours=hours, limit=500)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Date", "Level", "Action", "Message", "Actor"])
    for row in logs:
        actor = ""
        if row.actor and row.actor.email:
            actor = row.actor.email
        elif row.user and row.user.email:
            actor = row.user.email
        writer.writerow([
            row.created_at.isoformat() if row.created_at else "",
            row.level or "",
            row.action or "",
            (row.message or "")[:500],
            actor,
        ])
    filename = f"activity-logs-{hours}h.csv"
    return buf.getvalue().encode("utf-8-sig"), filename
