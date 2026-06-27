"""Pipeline export unifié — limite, normalisation, cache, PDF."""

from __future__ import annotations

import logging
from typing import Any

from app.services.ai_assistant.entity_memory import EntityMemory, is_contextual_reference
from app.services.ai_assistant.export_dataset_cache import store_export_dataset
from app.services.ai_assistant.export_normalize import (
    ExportDataError,
    normalize_items_for_export,
    parse_export_limit,
    resolve_export_limit_for_turn,
    validate_export_dataset,
)
from app.services.copilot_export_service import (
    build_context_export_pdf_from_items,
    build_export_download_spec,
    generate_module_pdf,
)

logger = logging.getLogger(__name__)

_EXPORT_TOOL_NAMES = {
    "notifications": "export_notifications_pdf",
    "tracking": "export_tracking_status_pdf",
    "users": "export_users_pdf",
    "tickets": "export_tickets_pdf",
    "conversations": "export_conversations_pdf",
    "logs": "export_activity_logs_pdf",
}


def prepare_export_dataset(
    raw_items: list[dict[str, Any]],
    *,
    module: str,
    message: str,
    admin_id: int,
    contextual: bool,
    state_limit: int | None,
    explicit_limit: int | None = None,
    source: str = "context_memory",
    fmt: str = "pdf",
    generated_by: str = "Administrateur Globex",
) -> tuple[list[dict[str, str]], int, str, bytes, str]:
    """
    Prépare le dataset export : limite → normalisation → validation → PDF.
    Retourne (normalized_items, limit_applied, filename, pdf_bytes, export_token).
    """
    count_before = len(raw_items)
    limit = resolve_export_limit_for_turn(
        message,
        items_count=count_before,
        contextual=contextual,
        state_limit=state_limit,
        explicit_limit=explicit_limit or parse_export_limit(message),
    )
    sliced = list(raw_items[:limit]) if limit else list(raw_items)

    logger.info(
        "[EXPORT] requested_type=%s requested_limit=%s source=%s "
        "dataset_count_before=%s dataset_count_after_limit=%s",
        module,
        limit,
        source,
        count_before,
        len(sliced),
    )

    normalized = validate_export_dataset(sliced, module)

    if normalized:
        logger.info(
            "[EXPORT] first_item_keys=%s normalized_first_item=%s",
            list(normalized[0].keys()),
            {k: (str(v)[:60] if v else "-") for k, v in normalized[0].items()},
        )

    pdf_bytes, filename = generate_module_pdf(
        sliced,
        module=module,
        generated_by=generated_by,
    )
    if fmt == "xlsx":
        if filename.lower().endswith(".pdf"):
            filename = filename[:-4] + ".xlsx"
        elif not filename.lower().endswith(".xlsx"):
            filename = f"{filename}.xlsx"
    logger.info(
        "[EXPORT] generated=true module=%s fmt=%s records=%s file=%s",
        module,
        fmt,
        len(normalized),
        filename,
    )

    export_token = store_export_dataset(
        admin_id=admin_id,
        module=module,
        items=normalized,
        limit=len(normalized),
        source=source,
        filename=filename,
        fmt=fmt,
        meta={"raw_count_before": count_before},
    )

    return normalized, len(normalized), filename, pdf_bytes, export_token


def build_export_response_spec(
    *,
    module: str,
    filename: str,
    records: int,
    export_token: str,
    fmt: str = "pdf",
    limit: int | None = None,
) -> dict[str, Any]:
    preset_map = {
        "notifications": "admin_notifications",
        "users": "admin_users",
        "tickets": "admin_tickets",
        "conversations": "admin_conversations",
        "tracking": "admin_tracking",
        "logs": "admin_logs",
    }
    preset = preset_map.get(module, f"admin_{module}")
    return build_export_download_spec(
        preset=preset,
        filename=filename,
        fmt=fmt,
        limit=limit or records,
        module=module,
        context_items=records,
        export_token=export_token,
        records=records,
    )


def export_tool_name(module: str, fmt: str = "pdf") -> str:
    if module == "logs":
        return "export_activity_logs_excel" if fmt == "xlsx" else "export_activity_logs_pdf"
    return _EXPORT_TOOL_NAMES.get(module, "export_context_pdf")


def generate_pdf_from_cache(
    cached: dict[str, Any],
    *,
    generated_by: str = "Administrateur Globex",
) -> tuple[bytes, str]:
    """Génère PDF depuis entrée cache."""
    prebuilt = cached.get("pdf_bytes")
    if prebuilt:
        return bytes(prebuilt), str(cached.get("filename") or "document.pdf")
    module = cached["module"]
    items = cached["items"]
    return build_context_export_pdf_from_items(items, module=module, generated_by=generated_by)


def generate_xlsx_from_cache(cached: dict[str, Any]) -> tuple[bytes, str]:
    """Génère XLSX depuis entrée cache (utilisateurs suspendus, etc.)."""
    import io

    import openpyxl
    from openpyxl.styles import Font

    items = cached.get("items") or []
    filename = cached.get("filename") or "export.xlsx"
    module = cached.get("module") or "generic"

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = module[:31] or "Export"

    if items:
        headers = list(items[0].keys())
        ws.append(headers)
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for row in items:
            ws.append([row.get(h, "") for h in headers])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue(), filename
