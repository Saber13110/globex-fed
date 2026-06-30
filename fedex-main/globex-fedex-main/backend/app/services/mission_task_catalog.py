"""Catalogue des tâches mission — source de vérité backend."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Types canoniques (UI + validation). Legacy : notifications → security, summary → reports.
CANONICAL_AGENT_TYPES = frozenset({"logs", "support", "users", "security", "tracking", "reports"})
LEGACY_AGENT_ALIASES: dict[str, str] = {
    "notifications": "security",
    "summary": "reports",
}
RUNTIME_AGENT_ALIASES: dict[str, str] = {
    "security": "notifications",
    "reports": "summary",
}

AGENT_LABELS: dict[str, str] = {
    "logs": "Logs Agent",
    "support": "Support Agent",
    "users": "Users Agent",
    "security": "Security Agent",
    "tracking": "Tracking Agent",
    "reports": "Reports Agent",
    "notifications": "Security Agent",
    "summary": "Reports Agent",
}


@dataclass(frozen=True)
class MissionTaskSpec:
    task_id: str
    agent_type: str
    label: str
    default_prompt: str
    action_type: str
    tool_hint: str | None = None
    requires_description: bool = False
    # Phase 1 — métadonnées chaînage (comportement runtime inchangé tant que non consommées)
    consumes_prior: bool = False
    produces_context: bool = True
    terminal: bool = False


def normalize_agent_type(agent_type: str) -> str:
    """Type canonique pour catalogue / validation."""
    key = (agent_type or "").strip().lower()
    return LEGACY_AGENT_ALIASES.get(key, key)


def runtime_agent_type(agent_type: str) -> str:
    """Type attendu par admin_agent_runtime (compatibilité legacy)."""
    canonical = normalize_agent_type(agent_type)
    return RUNTIME_AGENT_ALIASES.get(canonical, canonical)


def _task(
    task_id: str,
    agent_type: str,
    label: str,
    default_prompt: str,
    action_type: str,
    *,
    tool_hint: str | None = None,
    requires_description: bool = False,
    consumes_prior: bool = False,
    produces_context: bool = True,
    terminal: bool = False,
) -> MissionTaskSpec:
    return MissionTaskSpec(
        task_id=task_id,
        agent_type=agent_type,
        label=label,
        default_prompt=default_prompt,
        action_type=action_type,
        tool_hint=tool_hint,
        requires_description=requires_description,
        consumes_prior=consumes_prior,
        produces_context=produces_context,
        terminal=terminal,
    )


MISSION_TASKS: tuple[MissionTaskSpec, ...] = (
    # Logs — entrées : list / anomalies ; consommateurs : detail / summary / suspend
    _task("log_list", "logs", "Lister les logs", "Lister les derniers logs d'activité de la plateforme.", "analyze_logs"),
    _task(
        "log_detail",
        "logs",
        "Détail d'un log",
        "Afficher le détail d'un événement du journal d'activité récent.",
        "analyze_logs",
        consumes_prior=True,
    ),
    _task("log_anomalies", "logs", "Détecter anomalies", "Détecter les anomalies et alertes WARNING/CRITICAL dans les logs.", "analyze_logs"),
    _task(
        "log_summary",
        "logs",
        "Synthèse logs",
        "Produire une synthèse des événements importants du journal.",
        "analyze_logs",
        consumes_prior=True,
    ),
    _task(
        "log_export_pdf",
        "logs",
        "Export PDF logs",
        "Exporter le journal d'activité en fichier PDF téléchargeable.",
        "export_activity_logs_pdf",
        tool_hint="export_activity_logs_pdf",
        produces_context=False,
        terminal=True,
    ),
    _task(
        "log_export_excel",
        "logs",
        "Export Excel logs",
        "Exporter le journal d'activité en fichier Excel téléchargeable.",
        "export_activity_logs_excel",
        tool_hint="export_activity_logs_excel",
        produces_context=False,
        terminal=True,
    ),
    _task(
        "log_suspend_user",
        "logs",
        "Suspendre depuis log",
        "Identifier un utilisateur suspect dans les logs et préparer une suspension.",
        "suspend_user",
        tool_hint="suspend_user",
        requires_description=True,
        consumes_prior=True,
        produces_context=False,
        terminal=True,
    ),
    _task("custom", "logs", "Tâche libre", "", "analyze_logs", requires_description=True),
    # Support
    _task("ticket_list", "support", "Tickets ouverts", "Lister les tickets support ouverts et leurs priorités.", "analyze_tickets"),
    _task(
        "ticket_detail",
        "support",
        "Détail ticket",
        "Analyser en détail un ticket support spécifique.",
        "analyze_tickets",
        requires_description=True,
        consumes_prior=True,
    ),
    _task(
        "ticket_reply",
        "support",
        "Répondre ticket",
        "Préparer une réponse au ticket client indiqué.",
        "send_support_reply",
        requires_description=True,
        consumes_prior=True,
        produces_context=False,
        terminal=True,
    ),
    _task(
        "ticket_resolve",
        "support",
        "Clore ticket",
        "Marquer comme résolu le ticket support indiqué.",
        "resolve_ticket",
        requires_description=True,
        consumes_prior=True,
        produces_context=False,
        terminal=True,
    ),
    _task("custom", "support", "Tâche libre", "", "analyze_tickets", requires_description=True),
    # Users
    _task("user_list", "users", "Lister utilisateurs", "Lister les comptes utilisateurs et leurs statuts.", "analyze_users"),
    _task(
        "user_detail",
        "users",
        "Fiche utilisateur",
        "Afficher le détail d'un compte utilisateur.",
        "analyze_users",
        requires_description=True,
        consumes_prior=True,
    ),
    _task(
        "user_logs",
        "users",
        "Logs utilisateur",
        "Analyser l'activité récente d'un utilisateur.",
        "analyze_users",
        requires_description=True,
        consumes_prior=True,
    ),
    _task(
        "user_permissions",
        "users",
        "Permissions",
        "Vérifier les permissions et le rôle d'un utilisateur.",
        "analyze_users",
        requires_description=True,
        consumes_prior=True,
    ),
    _task(
        "user_suspend",
        "users",
        "Suspendre compte",
        "Suspendre le compte utilisateur indiqué.",
        "suspend_user",
        requires_description=True,
        consumes_prior=True,
        produces_context=False,
        terminal=True,
    ),
    _task(
        "user_reactivate",
        "users",
        "Réactiver compte",
        "Réactiver le compte utilisateur indiqué.",
        "reactivate_user",
        requires_description=True,
        consumes_prior=True,
        produces_context=False,
        terminal=True,
    ),
    _task(
        "user_delete",
        "users",
        "Supprimer compte",
        "Préparer la suppression du compte utilisateur indiqué.",
        "delete_user",
        requires_description=True,
        consumes_prior=True,
        produces_context=False,
        terminal=True,
    ),
    _task(
        "user_reset_password",
        "users",
        "Reset mot de passe",
        "Préparer la réinitialisation du mot de passe.",
        "reset_password",
        requires_description=True,
        consumes_prior=True,
        produces_context=False,
        terminal=True,
    ),
    _task("custom", "users", "Tâche libre", "", "analyze_users", requires_description=True),
    # Security (runtime alias notifications)
    _task("incident_list", "security", "Incidents sécurité", "Lister les incidents de sécurité récents.", "analyze_security", tool_hint="analyze_security"),
    _task(
        "incident_detail",
        "security",
        "Détail incident",
        "Analyser un incident de sécurité spécifique.",
        "analyze_security",
        tool_hint="analyze_security",
        requires_description=True,
        consumes_prior=True,
    ),
    _task(
        "incident_summary",
        "security",
        "Synthèse sécurité",
        "Synthétiser l'état de la sécurité et les menaces détectées.",
        "analyze_security",
        tool_hint="analyze_security",
        consumes_prior=True,
    ),
    _task("security_scan", "security", "Scan sécurité", "Lancer une analyse des tentatives d'intrusion et alertes IDS.", "analyze_security", tool_hint="analyze_security"),
    _task(
        "security_report",
        "security",
        "Rapport sécurité",
        "Produire un rapport des alertes et incidents de sécurité.",
        "analyze_security",
        tool_hint="analyze_security",
        consumes_prior=True,
        produces_context=False,
        terminal=True,
    ),
    _task(
        "notif_list",
        "security",
        "Notifications plateforme",
        "Lister les notifications admin non lues.",
        "analyze_notifications",
        tool_hint="analyze_notifications",
        produces_context=False,
    ),
    _task("custom", "security", "Tâche libre", "", "analyze_security", requires_description=True),
    # Tracking
    _task("tracking_analyze", "tracking", "Analyser expéditions", "Analyser les expéditions en cours et détecter les retards.", "analyze_tracking"),
    _task(
        "tracking_export_excel",
        "tracking",
        "Export Excel tracking",
        "Exporter les données de suivi en Excel.",
        "export_tracking_excel",
        tool_hint="export_tracking_excel",
        consumes_prior=True,
        produces_context=False,
        terminal=True,
    ),
    _task(
        "tracking_export_email",
        "tracking",
        "Export e-mail tracking",
        "Exporter les données de suivi et les envoyer par e-mail.",
        "export_and_email_tracking",
        tool_hint="export_and_email_tracking",
        consumes_prior=True,
        produces_context=False,
        terminal=True,
    ),
    _task("custom", "tracking", "Tâche libre", "", "analyze_tracking", requires_description=True),
    # Reports (runtime : summary)
    _task("report_list", "reports", "Lister rapports", "Lister les rapports disponibles.", "generate_summary"),
    _task(
        "report_preview",
        "reports",
        "Aperçu rapport",
        "Prévisualiser le contenu d'un rapport.",
        "generate_summary",
        requires_description=True,
        consumes_prior=True,
    ),
    _task(
        "report_redownload",
        "reports",
        "Retélécharger rapport",
        "Retélécharger un rapport exporté précédemment.",
        "generate_summary",
        requires_description=True,
        produces_context=False,
    ),
    _task(
        "report_share",
        "reports",
        "Partager rapport",
        "Partager un rapport avec un destinataire.",
        "generate_summary",
        requires_description=True,
        consumes_prior=True,
        produces_context=False,
        terminal=True,
    ),
    _task("custom", "reports", "Tâche libre", "", "generate_summary", requires_description=True),
)

_TASK_INDEX: dict[tuple[str, str], MissionTaskSpec] = {
    (spec.agent_type, spec.task_id): spec for spec in MISSION_TASKS
}


AGENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "logs": (
        "log", "logs", "journal", "audit", "activité", "activite", "anomalie",
        "erreur", "warning", "critical", "événement", "evenement", "historique",
        "pdf", "télécharger", "telecharger", "export", "fichier", "download",
    ),
    "support": (
        "ticket", "support", "client", "réponse", "reponse", "urgent", "plainte",
        "aide", "demande", "message client",
    ),
    "users": (
        "utilisateur", "user", "compte", "employé", "employe", "suspend",
        "inactif", "permission", "rôle", "role", "invitation",
    ),
    "security": (
        "notification", "alerte", "attaque", "attack", "sécurité", "securite",
        "incident", "ids", "tentative", "intrusion", "menace",
    ),
    "tracking": (
        "tracking", "colis", "expédition", "expedition", "livraison", "fedex",
        "retard", "shipment", "numéro de suivi", "numero de suivi",
    ),
    "reports": (
        "résumé", "resume", "synthèse", "synthese", "rapport", "bilan",
        "overview", "global", "jour", "semaine", "performance",
    ),
}


def get_task_spec(agent_type: str, task_id: str) -> MissionTaskSpec | None:
    canonical = normalize_agent_type(agent_type)
    return _TASK_INDEX.get((canonical, (task_id or "").strip()))


def tasks_for_agent(agent_type: str) -> list[MissionTaskSpec]:
    canonical = normalize_agent_type(agent_type)
    return [t for t in MISSION_TASKS if t.agent_type == canonical]


def chain_metadata_for_task(agent_type: str, task_id: str) -> dict[str, bool]:
    """Métadonnées chaînage pour une tâche catalogue (valeurs sûres si inconnue)."""
    spec = get_task_spec(agent_type, task_id)
    if not spec:
        return {"consumes_prior": False, "produces_context": False, "terminal": False}
    return {
        "consumes_prior": spec.consumes_prior,
        "produces_context": spec.produces_context,
        "terminal": spec.terminal,
    }


def catalog_for_api() -> list[dict[str, Any]]:
    """Liste sérialisable pour l'API / miroir frontend."""
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for spec in MISSION_TASKS:
        key = (spec.agent_type, spec.task_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "task_id": spec.task_id,
                "agent_type": spec.agent_type,
                "label": spec.label,
                "default_prompt": spec.default_prompt,
                "action_type": spec.action_type,
                "requires_description": spec.requires_description,
                "consumes_prior": spec.consumes_prior,
                "produces_context": spec.produces_context,
                "terminal": spec.terminal,
            }
        )
    return out
