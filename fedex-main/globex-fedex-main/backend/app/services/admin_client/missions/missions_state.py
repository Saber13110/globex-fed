"""Machine à états — actions Mission Control."""

from __future__ import annotations

_RETRY_ALLOWED = frozenset(
    {"draft", "scheduled", "failed", "waiting_permission", "waiting_plan_approval"}
)
_RESUME_ALLOWED = frozenset({"paused"})
_CANCEL_FORBIDDEN = frozenset({"completed", "cancelled"})
_DELETE_ALLOWED = frozenset({"draft", "failed", "cancelled"})


def validate_retry(status: str) -> str | None:
    if status in _RETRY_ALLOWED:
        return None
    if status == "paused":
        return (
            "Cette mission est en pause — utilisez « reprendre la mission » (resume), "
            "pas « relancer »."
        )
    if status == "running":
        return "Mission déjà en cours d'exécution."
    if status == "completed":
        return "Mission déjà terminée — consultez les résultats."
    return f"Impossible de relancer une mission au statut « {status} »."


def validate_resume(status: str) -> str | None:
    if status in _RESUME_ALLOWED:
        return None
    if status == "failed":
        return "Mission échouée — utilisez « relancer la mission #id » (retry)."
    return f"Seule une mission en pause peut être reprise (statut actuel : {status})."


def validate_cancel(status: str) -> str | None:
    if status in _CANCEL_FORBIDDEN:
        return f"Impossible d'annuler — mission déjà {status}."
    return None


def validate_delete(status: str) -> str | None:
    if status in _DELETE_ALLOWED:
        return None
    if status == "completed":
        return "Impossible de supprimer une mission terminée."
    return (
        f"Suppression refusée pour le statut « {status} ». "
        "Seules les missions brouillon, échouées ou annulées peuvent être supprimées."
    )
