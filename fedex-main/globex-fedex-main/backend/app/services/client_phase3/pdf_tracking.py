"""PDF suivi colis — données serveur uniquement (pas de contenu inventé par le LLM)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.chat_session import ChatSession
from app.models.user import User
from app.services.chat_export_service import session_tracking_numbers
from app.services.client_phase3.export_intent import tracking_pdf_preset
from app.services.gpt.orchestrator import SLUG_CLIENT
from app.services.gpt.tool_executor import execute_tool
from app.services.gpt.tool_types import ToolCall, ToolExecutionContext
from app.services.llm.tracking_extract import extract_tracking_number
from app.utils.tracking_parser import is_plausible_tracking_number


def _tool_context(db: Session, user: User, session: ChatSession, ui_language: str | None) -> ToolExecutionContext:
    lang = (ui_language or user.preferred_language or "fr").lower()[:2]
    return ToolExecutionContext(
        db=db,
        user_id=user.id,
        user_role="client",
        gpt_slug=SLUG_CLIENT,
        ui_language=lang,
        analysis_mode=False,
        skip_approval=True,
        session_id=session.id,
    )


def run_tracking_pdf_export(
    db: Session,
    user: User,
    session: ChatSession,
    message: str,
    *,
    ui_language: str | None,
) -> tuple[str, dict[str, Any] | None, str | None]:
    """
    Retourne (reply, export_download, tracking_number).
  """
    tn = extract_tracking_number(message or "")
    if tn and not is_plausible_tracking_number(tn):
        tn = None

    session_tns = session_tracking_numbers(db, session.id, user.id)
    scope = "session" if session_tns or tn else "recent"
    preset = tracking_pdf_preset(message)

    args: dict[str, Any] = {"scope": scope, "preset": preset, "limit": 50}
    if tn:
        args["tracking_number"] = tn

    result = execute_tool(
        _tool_context(db, user, session, ui_language),
        ToolCall(name="client_export_tracking_pdf", args=args),
    )

    if not result.success:
        err = result.error or "Impossible de préparer l'export PDF."
        data = result.data or {}
        if data.get("error_code") == "no_parcels":
            hint = (
                "Aucun colis enregistré pour cet export. "
                "Consultez d'abord un numéro de suivi dans le chat, puis redemandez le PDF."
            )
            if tn:
                hint = (
                    f"Aucune donnée de suivi enregistrée pour **{tn}**. "
                    "Demandez d'abord le statut de ce colis, puis réessayez l'export PDF."
                )
            return hint, None, tn
        return err, None, tn

    export_dl = result.data.get("export_download")
    if not export_dl:
        return "L'export PDF n'a pas pu être préparé.", None, tn

    tns = export_dl.get("tracking_numbers") or []
    tracking_number = tns[0] if len(tns) == 1 else (tn or (tns[0] if tns else None))
    count = len(tns)
    label = tracking_number if count <= 1 else f"{count} colis"
    reply = (
        f"Votre export PDF pour **{label}** est prêt.\n\n"
        "Le document contient les **données de suivi FedEx** (statut, localisation, historique des scans) "
        "— pas le texte brut de la conversation.\n\n"
        "Utilisez le lien de téléchargement ci-dessous."
    )
    return reply, export_dl, tracking_number
