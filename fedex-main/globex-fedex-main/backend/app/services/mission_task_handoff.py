"""Compatibilité des enchaînements tâche → tâche (agents différents ou non)."""

from __future__ import annotations

from app.services.mission_task_catalog import AGENT_LABELS, get_task_spec, normalize_agent_type

# Tâches productrices connues → paires (agent, task_id) autorisées en étape suivante (si consumes_prior).
HANDOFF_ALLOWED: dict[tuple[str, str], frozenset[tuple[str, str]]] = {
    ("security", "incident_list"): frozenset(
        {
            ("security", "incident_detail"),
            ("security", "incident_summary"),
            ("security", "security_report"),
            ("security", "security_scan"),
            ("security", "custom"),
            ("users", "user_detail"),
            ("users", "user_logs"),
            ("users", "user_suspend"),
            ("users", "custom"),
            ("support", "ticket_detail"),
            ("support", "ticket_reply"),
            ("support", "custom"),
        }
    ),
    ("security", "incident_detail"): frozenset(
        {
            ("security", "security_report"),
            ("security", "incident_summary"),
            ("security", "custom"),
            ("users", "user_detail"),
            ("users", "user_logs"),
            ("support", "ticket_detail"),
            ("support", "ticket_reply"),
            ("support", "custom"),
        }
    ),
    ("logs", "log_list"): frozenset(
        {
            ("logs", "log_detail"),
            ("logs", "log_summary"),
            ("logs", "log_anomalies"),
            ("logs", "log_suspend_user"),
            ("logs", "custom"),
            ("users", "user_detail"),
            ("users", "custom"),
        }
    ),
    ("logs", "log_anomalies"): frozenset(
        {
            ("logs", "log_detail"),
            ("logs", "log_summary"),
            ("logs", "log_suspend_user"),
            ("logs", "custom"),
        }
    ),
    ("support", "ticket_list"): frozenset(
        {
            ("support", "ticket_detail"),
            ("support", "ticket_reply"),
            ("support", "ticket_resolve"),
            ("support", "custom"),
            ("users", "user_detail"),
            ("users", "user_logs"),
        }
    ),
    ("support", "ticket_detail"): frozenset(
        {
            ("support", "ticket_reply"),
            ("support", "ticket_resolve"),
            ("support", "custom"),
            ("users", "user_detail"),
            ("users", "user_logs"),
            ("users", "user_permissions"),
        }
    ),
    ("users", "user_list"): frozenset(
        {
            ("users", "user_detail"),
            ("users", "user_logs"),
            ("users", "user_permissions"),
            ("users", "user_suspend"),
            ("users", "custom"),
        }
    ),
}


def validate_task_handoff(
    prior_agent: str | None,
    prior_task_id: str | None,
    next_agent: str,
    next_task_id: str | None,
    *,
    has_prior_output: bool = False,
) -> str | None:
    """
    Retourne un message d'erreur si l'enchaînement est incohérent, sinon None.
    Ne bloque que les producteurs listés dans HANDOFF_ALLOWED.
    """
    if not has_prior_output or not prior_agent or not prior_task_id:
        return None

    prior_key = (normalize_agent_type(prior_agent), prior_task_id)
    allowed = HANDOFF_ALLOWED.get(prior_key)
    if allowed is None:
        return None

    next_canonical = normalize_agent_type(next_agent)
    next_tid = (next_task_id or "custom").strip() or "custom"
    next_key = (next_canonical, next_tid)
    if next_key in allowed:
        return None

    prior_spec = get_task_spec(prior_key[0], prior_key[1])
    next_spec = get_task_spec(next_canonical, next_tid if next_tid != "custom" else "custom")
    prior_label = prior_spec.label if prior_spec else prior_key[1]
    next_label = next_spec.label if next_spec else next_tid
    prior_agent_label = AGENT_LABELS.get(prior_key[0], prior_key[0])
    next_agent_label = AGENT_LABELS.get(next_canonical, next_canonical)

    if prior_key == ("security", "incident_list") and next_canonical == "logs":
        return (
            f"**Enchaînement impossible** — « {next_label} » ({next_agent_label}) ne traite pas "
            f"une liste d'incidents sécurité.\n\n"
            f"Vous avez demandé un détail d'**incident #4** : ce n'est pas un événement du "
            f"journal d'activité (Logs).\n\n"
            f"**Après « {prior_label} »**, utilisez plutôt :\n"
            "- **Security Agent** → **Détail incident** — précisions : `#4` (4ᵉ ligne) ou `incident #12`\n"
            "- **Support Agent** → **Détail ticket** (client issu des incidents)\n"
            "- **Users Agent** → **Fiche utilisateur** (e-mail `amine@gmail.com`)\n\n"
            "_Ne reliez pas Logs « Détail d'un log » après une liste d'incidents IDS._"
        )

    return (
        f"**Enchaînement incompatible** — « {next_label} » ({next_agent_label}) ne peut pas "
        f"exploiter directement le résultat de « {prior_label} » ({prior_agent_label}).\n\n"
        "Choisissez une tâche prévue pour la suite de cette étape, ou modifiez le workflow."
    )
