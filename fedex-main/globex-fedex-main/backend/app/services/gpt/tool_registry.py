"""Registre central des outils GPT — déclarations pour Gemini function calling."""

from __future__ import annotations

import json
from typing import Any

from app.models.gpt_definition import GptDefinition
from app.services.gpt.tool_types import ToolDefinition

_ROLE_ADMIN = frozenset({"admin"})
_ROLE_CLIENT = frozenset({"client", "employee"})
_ROLE_ALL = frozenset({"admin", "client", "employee"})

_OBJ = {"type": "object", "properties": {}, "required": []}


def _schema(props: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": props,
        "required": required or [],
    }


# --- Définitions déclaratives ---

TOOL_DEFINITIONS: list[ToolDefinition] = [
    ToolDefinition(
        name="get_platform_stats",
        description="Lit les KPIs temps réel de la plateforme Globex (utilisateurs, expéditions, incidents, requêtes FedEx).",
        parameters=_schema({}),
        allowed_roles=_ROLE_ADMIN,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="analyze_tracking",
        description=(
            "Lit les expéditions/colis en base : statuts FedEx, retards, volumes récents, "
            "utilisateur lié (nom, e-mail). À utiliser pour : colis, suivi, tracking, "
            "expéditions, retards, statuts, derniers numéros suivis, colis par utilisateur, "
            "colis en exception, « derniers colis suivis »."
        ),
        parameters=_schema(
            {
                "limit": {
                    "type": "integer",
                    "description": "Nombre max de lignes à analyser (défaut 30).",
                }
            }
        ),
        allowed_roles=_ROLE_ADMIN,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="analyze_tickets",
        description="Liste et résume les tickets support ouverts ou récents.",
        parameters=_schema(
            {
                "status": {
                    "type": "string",
                    "description": "open | all (défaut open).",
                },
                "limit": {"type": "integer", "description": "Max tickets (défaut 20)."},
            }
        ),
        allowed_roles=_ROLE_ADMIN,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="analyze_users",
        description=(
            "Liste et statistiques des comptes utilisateurs. À utiliser pour : utilisateurs, "
            "comptes, admins, clients, employés, comptes actifs/suspendus/désactivés, "
            "inscriptions récentes, rôles. Filtres : role=admin|client|employe, "
            "status=active|suspended. Ne pas utiliser pour le suivi colis FedEx."
        ),
        parameters=_schema(
            {
                "role": {
                    "type": "string",
                    "description": "Filtre rôle : client | employe | admin (optionnel).",
                },
                "status": {
                    "type": "string",
                    "description": "Filtre statut : active | suspended | pending | invited (optionnel).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Nombre max de comptes listés (défaut 50, max 200).",
                },
            }
        ),
        allowed_roles=_ROLE_ADMIN,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="analyze_logs",
        description=(
            "Lit les journaux d'activité admin sur une période. À utiliser pour : logs, "
            "journaux, activité système, actions admin, historique d'activité, erreurs, audit."
        ),
        parameters=_schema(
            {
                "hours": {
                    "type": "integer",
                    "description": "Fenêtre en heures (1–168, défaut 24).",
                },
                "limit": {"type": "integer", "description": "Max entrées (défaut 50)."},
            }
        ),
        allowed_roles=_ROLE_ADMIN,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="analyze_notifications",
        description=(
            "Liste les notifications admin récentes. À utiliser pour : notifications, alertes, "
            "événements récents, activité récente, choses importantes, incidents signalés, "
            "informations à surveiller, « qu'est-ce qui s'est passé récemment », "
            "« y a-t-il quelque chose à surveiller »."
        ),
        parameters=_schema(
            {
                "limit": {"type": "integer", "description": "Nombre max (défaut 10)."},
                "unread_only": {"type": "boolean", "description": "Uniquement les non lues."},
                "critical_only": {"type": "boolean", "description": "Priorité critique uniquement."},
            }
        ),
        allowed_roles=_ROLE_ADMIN,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="analyze_conversations",
        description=(
            "Liste les conversations chat clients/employés (titre, aperçu, utilisateur, "
            "catégorie, statut). Utilisez pour « conversations de tous les utilisateurs »."
        ),
        parameters=_schema(
            {
                "limit": {"type": "integer", "description": "Nombre max (défaut 30)."},
                "search": {"type": "string", "description": "Filtre texte optionnel."},
                "user_id": {"type": "integer", "description": "Filtrer par ID utilisateur."},
            }
        ),
        allowed_roles=_ROLE_ADMIN,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="search_knowledge",
        description=(
            "Recherche sémantique dans la base de connaissances GPT. À utiliser pour : "
            "documents, base de connaissances, fichiers uploadés, documentation, procédures, "
            "politiques internes — pas pour les données live plateforme (users, colis, logs)."
        ),
        parameters=_schema(
            {
                "query": {
                    "type": "string",
                    "description": "Question ou mots-clés à rechercher.",
                },
                "limit": {"type": "integer", "description": "Nombre max de passages (défaut 5)."},
            },
            required=["query"],
        ),
        allowed_roles=_ROLE_ADMIN,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="list_knowledge_documents",
        description="Liste les documents indexés dans la base de connaissances GPT admin.",
        parameters=_schema(
            {
                "limit": {"type": "integer", "description": "Nombre max (défaut 25)."},
            }
        ),
        allowed_roles=_ROLE_ADMIN,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="analyze_reports",
        description=(
            "Synthèse rapport opérationnel : KPI plateforme + aperçu tracking, tickets ouverts. "
            "Lecture seule — pour questions « rapport », « bilan », « vue d'ensemble »."
        ),
        parameters=_schema(
            {
                "tracking_limit": {"type": "integer", "description": "Lignes tracking (défaut 10)."},
                "ticket_limit": {"type": "integer", "description": "Tickets récents (défaut 10)."},
            }
        ),
        allowed_roles=_ROLE_ADMIN,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="analyze_security",
        description=(
            "Incidents sécurité IDS ouverts/récents, menaces prompt injection, alertes critiques."
        ),
        parameters=_schema(
            {
                "status": {
                    "type": "string",
                    "description": "open | all (défaut open).",
                },
                "limit": {"type": "integer", "description": "Max incidents (défaut 15)."},
            }
        ),
        allowed_roles=_ROLE_ADMIN,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="export_activity_logs_pdf",
        description=(
            "ACTION — Génère un export PDF des journaux d'activité admin (mode Agent requis)."
        ),
        parameters=_schema(
            {
                "hours": {
                    "type": "integer",
                    "description": "Période en heures (défaut 24).",
                }
            }
        ),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="write",
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="export_activity_logs_excel",
        description=(
            "ACTION — Export Excel (.xlsx) des journaux d'activité admin (mode Agent requis)."
        ),
        parameters=_schema(
            {
                "hours": {
                    "type": "integer",
                    "description": "Période en heures (défaut 24).",
                }
            }
        ),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="write",
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="fedex_track_package",
        description="Suivi FedEx temps réel d'un colis par numéro de suivi (12–22 chiffres).",
        parameters=_schema(
            {
                "tracking_number": {
                    "type": "string",
                    "description": "Numéro de suivi FedEx.",
                }
            },
            required=["tracking_number"],
        ),
        allowed_roles=_ROLE_ALL,
        gpt_slugs=frozenset({"fedex-admin-ops", "fedex-client"}),
    ),
    ToolDefinition(
        name="get_tracking_by_number",
        description=(
            "Recherche précise d'un colis par numéro : statut, localisation, utilisateur lié, historique."
        ),
        parameters=_schema(
            {
                "tracking_number": {
                    "type": "string",
                    "description": "Numéro de suivi FedEx (10–22 chiffres).",
                }
            },
            required=["tracking_number"],
        ),
        allowed_roles=_ROLE_ADMIN,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="get_admin_users",
        description="Liste les comptes administrateur actifs ou suspendus.",
        parameters=_schema(
            {
                "limit": {"type": "integer", "description": "Nombre max (défaut 30)."},
            }
        ),
        allowed_roles=_ROLE_ADMIN,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="analyze_suspicious_logs",
        description=(
            "Analyse sécurité des journaux : échecs connexion, injections, erreurs, niveau de risque."
        ),
        parameters=_schema(
            {
                "hours": {"type": "integer", "description": "Période en heures (défaut 24)."},
            }
        ),
        allowed_roles=_ROLE_ADMIN,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="find_fedex_location",
        description="Recherche un centre ou point FedEx par ville, code postal ou adresse.",
        parameters=_schema(
            {
                "query": {
                    "type": "string",
                    "description": "Ville, code postal ou adresse à rechercher.",
                },
                "country_code": {
                    "type": "string",
                    "description": "Code pays ISO (défaut MA).",
                },
            },
            required=["query"],
        ),
        allowed_roles=_ROLE_ALL,
        gpt_slugs=frozenset({"fedex-admin-ops", "fedex-client"}),
    ),
    ToolDefinition(
        name="client_watch_shipment",
        description=(
            "Active la surveillance d'un colis FedEx pour le client "
            "(alertes e-mail et/ou in-app sur changement de statut)."
        ),
        parameters=_schema(
            {
                "tracking_number": {
                    "type": "string",
                    "description": "Numéro de suivi FedEx (12 à 14 chiffres).",
                },
                "notify_email": {
                    "type": "boolean",
                    "description": "Envoyer des alertes par e-mail (défaut true).",
                },
                "notify_in_app": {
                    "type": "boolean",
                    "description": "Notifications in-app (défaut true).",
                },
            },
            required=["tracking_number"],
        ),
        allowed_roles=frozenset({"client"}),
        gpt_slugs=frozenset({"fedex-client"}),
    ),
    ToolDefinition(
        name="client_open_support_ticket",
        description="Ouvre un ticket support admin pour le client (livraison, e-mail, etc.).",
        parameters=_schema(
            {
                "message": {
                    "type": "string",
                    "description": "Description du problème (min. 10 caractères).",
                },
                "tracking_number": {
                    "type": "string",
                    "description": "Numéro de suivi lié (optionnel).",
                },
                "category": {
                    "type": "string",
                    "description": "Catégorie : delivery, billing, account…",
                },
                "priority": {
                    "type": "string",
                    "description": "Priorité : low, medium, high.",
                },
            },
            required=["message"],
        ),
        allowed_roles=frozenset({"client"}),
        gpt_slugs=frozenset({"fedex-client"}),
    ),
    ToolDefinition(
        name="client_export_tracking_excel",
        description="Prépare un export Excel des suivis du client (session ou compte).",
        parameters=_schema(
            {
                "scope": {
                    "type": "string",
                    "description": "session | recent | all (défaut recent).",
                },
                "tracking_number": {
                    "type": "string",
                    "description": "Un seul colis (optionnel).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Nombre max de colis (défaut 20).",
                },
            },
        ),
        allowed_roles=frozenset({"client"}),
        gpt_slugs=frozenset({"fedex-client"}),
    ),
    ToolDefinition(
        name="client_export_tracking_pdf",
        description="Prépare un rapport PDF des suivis (résumé du jour ou historique).",
        parameters=_schema(
            {
                "scope": {
                    "type": "string",
                    "description": "session | recent | all (défaut recent).",
                },
                "preset": {
                    "type": "string",
                    "description": "tracking_summary (jour) ou tracking (historique).",
                },
                "tracking_number": {
                    "type": "string",
                    "description": "Un seul colis (optionnel).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Nombre max de colis (défaut 50).",
                },
            },
        ),
        allowed_roles=frozenset({"client"}),
        gpt_slugs=frozenset({"fedex-client"}),
    ),
    ToolDefinition(
        name="client_generate_text_pdf",
        description=(
            "Génère un PDF avec un texte libre (résumé conversation, contenu demandé par le client). "
            "Fournissez le texte complet à inclure dans le document."
        ),
        parameters=_schema(
            {
                "text": {"type": "string", "description": "Contenu texte du PDF."},
                "title": {"type": "string", "description": "Titre optionnel du document."},
            },
            required=["text"],
        ),
        allowed_roles=frozenset({"client"}),
        sensitivity="write",
        gpt_slugs=frozenset({"fedex-client"}),
    ),
    ToolDefinition(
        name="suspend_user",
        description="Suspend un compte utilisateur (action sensible — approbation requise).",
        parameters=_schema(
            {
                "user_id": {"type": "integer", "description": "ID utilisateur."},
                "email": {"type": "string", "description": "E-mail si ID inconnu."},
            }
        ),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="destructive",
        requires_approval=True,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="reactivate_user",
        description="Réactive un compte utilisateur suspendu (action sensible — approbation requise).",
        parameters=_schema(
            {
                "user_id": {"type": "integer", "description": "ID utilisateur."},
                "email": {"type": "string", "description": "E-mail si ID inconnu."},
            }
        ),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="destructive",
        requires_approval=True,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="create_ticket",
        description="ACTION — Crée un ticket support (mode Agent, approbation si configurée).",
        parameters=_schema(
            {
                "subject": {"type": "string", "description": "Sujet du ticket."},
                "description": {"type": "string", "description": "Description."},
                "user_id": {"type": "integer", "description": "ID utilisateur concerné (optionnel)."},
            },
            required=["subject"],
        ),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="write",
        requires_approval=True,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="send_notification",
        description="ACTION — Envoie une notification admin (mode Agent, approbation requise).",
        parameters=_schema(
            {
                "title": {"type": "string", "description": "Titre de la notification."},
                "message": {"type": "string", "description": "Corps du message."},
                "user_id": {"type": "integer", "description": "Destinataire (optionnel, tous si absent)."},
            },
            required=["title", "message"],
        ),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="write",
        requires_approval=True,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="run_security_scan",
        description="ACTION — Lance un scan sécurité IDS (mode Agent, approbation requise).",
        parameters=_schema({}),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="write",
        requires_approval=True,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="create_agent_mission",
        description="ACTION — Crée une mission Agent Missions automatisée (mode Agent, approbation).",
        parameters=_schema(
            {
                "title": {"type": "string", "description": "Titre de la mission."},
                "goal": {"type": "string", "description": "Objectif de la mission."},
                "agent_type": {
                    "type": "string",
                    "description": "Type agent : tracking | logs | users | summary | …",
                },
            },
            required=["title", "goal"],
        ),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="write",
        requires_approval=True,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="export_notifications_pdf",
        description=(
            "ACTION — Export PDF des notifications listées précédemment ou demandées "
            "(mode Agent). Ne pas utiliser pour simplement afficher les notifications."
        ),
        parameters=_schema(
            {"limit": {"type": "integer", "description": "Nombre max (défaut 10)."}}
        ),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="write",
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="export_tracking_pdf",
        description="ACTION — Export PDF des opérations tracking récentes (mode Agent).",
        parameters=_schema(
            {"limit": {"type": "integer", "description": "Nombre max (défaut 15)."}}
        ),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="write",
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="export_users_pdf",
        description="ACTION — Export PDF de la liste utilisateurs (mode Agent).",
        parameters=_schema(
            {
                "limit": {"type": "integer", "description": "Nombre max (défaut 50)."},
                "role": {"type": "string", "description": "Filtre rôle optionnel."},
            }
        ),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="write",
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="export_tickets_pdf",
        description="ACTION — Export PDF des tickets support (mode Agent).",
        parameters=_schema(
            {"limit": {"type": "integer", "description": "Nombre max (défaut 20)."}}
        ),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="write",
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="export_conversations_pdf",
        description="ACTION — Export PDF des conversations chat (mode Agent).",
        parameters=_schema(
            {"limit": {"type": "integer", "description": "Nombre max (défaut 30)."}}
        ),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="write",
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="export_generic_result_pdf",
        description=(
            "ACTION — Export PDF générique du dernier résultat affiché en session "
            "(mode Agent) quand aucun export spécialisé ne convient."
        ),
        parameters=_schema(
            {
                "module": {"type": "string", "description": "Module source (notifications, tracking…)."},
                "limit": {"type": "integer", "description": "Nombre max."},
            }
        ),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="write",
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="generate_text_pdf",
        description=(
            "ACTION — Génère un PDF contenant un texte libre fourni par l'utilisateur "
            "(ex. « génère un pdf avec bonjour »). Mode Agent requis."
        ),
        parameters=_schema(
            {
                "text": {"type": "string", "description": "Contenu texte du PDF."},
                "title": {"type": "string", "description": "Titre optionnel du document."},
            },
            required=["text"],
        ),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="write",
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="search_users",
        description="Recherche un utilisateur par e-mail, nom ou ID.",
        parameters=_schema(
            {
                "query": {"type": "string", "description": "E-mail, nom ou ID."},
                "limit": {"type": "integer", "description": "Max résultats (défaut 20)."},
            },
            required=["query"],
        ),
        allowed_roles=_ROLE_ADMIN,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="notify_admin",
        description="Crée une notification admin sur la plateforme (alerte, info, fin de tâche).",
        parameters=_schema(
            {
                "title": {"type": "string", "description": "Titre de l'alerte."},
                "message": {"type": "string", "description": "Corps du message."},
                "priority": {"type": "string", "description": "low|normal|high|critical"},
            },
            required=["title", "message"],
        ),
        allowed_roles=_ROLE_ADMIN,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="notify_user",
        description="Envoie une notification in-app à un utilisateur client.",
        parameters=_schema(
            {
                "user_id": {"type": "integer"},
                "email": {"type": "string"},
                "title": {"type": "string"},
                "message": {"type": "string"},
            },
            required=["title", "message"],
        ),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="write",
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="notify_employee",
        description="Envoie une notification in-app à un employé Globex.",
        parameters=_schema(
            {
                "user_id": {"type": "integer"},
                "email": {"type": "string"},
                "title": {"type": "string"},
                "message": {"type": "string"},
            },
            required=["title", "message"],
        ),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="write",
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="send_email",
        description="Envoie un e-mail SMTP réel à un destinataire.",
        parameters=_schema(
            {
                "to": {"type": "string", "description": "Adresse e-mail."},
                "subject": {"type": "string"},
                "body": {"type": "string", "description": "Corps texte."},
            },
            required=["to", "subject", "body"],
        ),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="write",
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="send_client_email",
        description="Envoie un e-mail SMTP à un client (retard, incident, documents).",
        parameters=_schema(
            {
                "to": {"type": "string"},
                "email": {"type": "string"},
                "user_id": {"type": "integer"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            required=["subject", "body"],
        ),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="write",
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="draft_client_email",
        description="Prépare un brouillon d'e-mail client sans envoi.",
        parameters=_schema(
            {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            }
        ),
        allowed_roles=_ROLE_ADMIN,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="reply_support_ticket",
        description="Publie une réponse admin sur un ticket support (notification client incluse).",
        parameters=_schema(
            {
                "ticket_id": {"type": "integer"},
                "reply_body": {"type": "string", "description": "Texte de la réponse."},
            },
            required=["ticket_id", "reply_body"],
        ),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="write",
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="close_ticket",
        description="Ferme un ticket support (statut closed).",
        parameters=_schema(
            {
                "ticket_id": {"type": "integer"},
                "resolution_note": {"type": "string", "description": "Note interne optionnelle."},
            },
            required=["ticket_id"],
        ),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="write",
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="escalate_ticket",
        description="Escalade un ticket (statut escalated, priorité haute, alerte admin).",
        parameters=_schema(
            {
                "ticket_id": {"type": "integer"},
                "reason": {"type": "string", "description": "Motif d'escalade."},
            },
            required=["ticket_id"],
        ),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="write",
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="draft_ticket_reply",
        description="Prépare un brouillon de réponse ticket sans publication.",
        parameters=_schema(
            {
                "ticket_id": {"type": "integer"},
                "reply_body": {"type": "string", "description": "Brouillon (optionnel)."},
            },
            required=["ticket_id"],
        ),
        allowed_roles=_ROLE_ADMIN,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="scan_ticket_sla",
        description="Liste les tickets actifs dépassant le SLA (retard de traitement).",
        parameters=_schema(
            {
                "limit": {"type": "integer", "description": "Nombre max de tickets (défaut 15)."},
            }
        ),
        allowed_roles=_ROLE_ADMIN,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="scan_dormant_accounts",
        description=(
            "Liste les comptes actifs sans activité depuis N jours (logs, sessions). "
            "Lecture seule — utile avant suspension en lot."
        ),
        parameters=_schema(
            {
                "days": {"type": "integer", "description": "Seuil d'inactivité en jours (défaut 30)."},
                "limit": {"type": "integer", "description": "Nombre max de comptes (défaut 20)."},
                "role": {"type": "string", "description": "Filtrer par rôle : client, employe."},
            }
        ),
        allowed_roles=_ROLE_ADMIN,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="notify_users_by_role",
        description=(
            "Diffuse une notification in-app à tous les utilisateurs actifs d'un rôle "
            "(client ou employe). Action sensible — approbation admin requise."
        ),
        parameters=_schema(
            {
                "role": {"type": "string", "description": "client ou employe"},
                "title": {"type": "string"},
                "message": {"type": "string"},
                "limit": {"type": "integer", "description": "Plafond destinataires (défaut 100)."},
            },
            required=["role", "title", "message"],
        ),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="write",
        requires_approval=True,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="notify_all_users",
        description=(
            "Diffuse une notification in-app à tous les utilisateurs actifs (hors admins). "
            "Approbation admin obligatoire."
        ),
        parameters=_schema(
            {
                "title": {"type": "string"},
                "message": {"type": "string"},
                "limit": {"type": "integer", "description": "Plafond destinataires (défaut 100)."},
            },
            required=["title", "message"],
        ),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="destructive",
        requires_approval=True,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="send_bulk_email",
        description=(
            "Envoie le même e-mail SMTP à plusieurs utilisateurs (filtre rôle ou liste d'IDs). "
            "Approbation admin obligatoire."
        ),
        parameters=_schema(
            {
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "role": {"type": "string", "description": "client ou employe (optionnel)."},
                "user_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Liste d'IDs utilisateurs (optionnel).",
                },
                "limit": {"type": "integer"},
            },
            required=["subject", "body"],
        ),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="destructive",
        requires_approval=True,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="suspend_users_bulk",
        description=(
            "Suspend plusieurs comptes (liste user_ids ou comptes dormants via dormant_days). "
            "Approbation admin obligatoire."
        ),
        parameters=_schema(
            {
                "user_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "IDs à suspendre.",
                },
                "dormant_days": {
                    "type": "integer",
                    "description": "Suspendre les comptes inactifs depuis N jours.",
                },
                "role": {"type": "string", "description": "Filtrer rôle si dormant_days."},
                "reason": {"type": "string"},
                "limit": {"type": "integer"},
            },
        ),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="destructive",
        requires_approval=True,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    # --- Phase 5 : catalogue 62 outils ---
    ToolDefinition(
        name="notify_admin_task_complete",
        description="Notifie l'admin qu'une tâche agent est terminée (lecture, pas d'approbation).",
        parameters=_schema(
            {
                "task": {"type": "string"},
                "summary": {"type": "string"},
                "message": {"type": "string"},
            },
            required=["summary"],
        ),
        allowed_roles=_ROLE_ADMIN,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="notify_user_warning",
        description="Envoie un avertissement sécurité à un utilisateur (approbation si initiative agent).",
        parameters=_schema(
            {
                "user_id": {"type": "integer"},
                "email": {"type": "string"},
                "title": {"type": "string"},
                "message": {"type": "string"},
            },
            required=["message"],
        ),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="write",
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="send_admin_email",
        description="Envoie un e-mail à tous les administrateurs actifs.",
        parameters=_schema(
            {
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "message": {"type": "string"},
            },
            required=["body"],
        ),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="write",
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="analyze_platform_health",
        description="Rapport composite santé plateforme (stats, tracking, users, tickets, sécurité).",
        parameters=_schema({}),
        allowed_roles=_ROLE_ADMIN,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="generate_security_report",
        description="Rapport sécurité complet : incidents ouverts, logs suspects, notifications critiques.",
        parameters=_schema({"hours": {"type": "integer", "description": "Fenêtre logs suspects (défaut 24h)."}}),
        allowed_roles=_ROLE_ADMIN,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="get_agent_missions_summary",
        description="Liste les missions agent récentes avec statuts.",
        parameters=_schema({"limit": {"type": "integer"}}),
        allowed_roles=_ROLE_ADMIN,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="analyze_weekly_activity",
        description="Synthèse activité hebdomadaire (logs + notifications).",
        parameters=_schema(
            {
                "hours": {"type": "integer", "description": "Période en heures (défaut 168)."},
                "limit": {"type": "integer"},
            }
        ),
        allowed_roles=_ROLE_ADMIN,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="get_security_alerts",
        description="Alias lecture des alertes sécurité ouvertes (incidents, tentatives suspectes).",
        parameters=_schema(
            {
                "status": {"type": "string", "description": "open, closed, all"},
                "limit": {"type": "integer"},
            }
        ),
        allowed_roles=_ROLE_ADMIN,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="get_workspace_briefing",
        description="Briefing workspace Jarvis : KPI, SLA, comptes dormants, approbations en attente.",
        parameters=_schema({}),
        allowed_roles=_ROLE_ADMIN,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="push_jarvis_alert",
        description="Pousse une alerte visible dans le workspace Jarvis (notification plateforme).",
        parameters=_schema(
            {
                "title": {"type": "string"},
                "message": {"type": "string"},
                "level": {"type": "string", "description": "low, normal, high, critical"},
            },
            required=["message"],
        ),
        allowed_roles=_ROLE_ADMIN,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="delete_user",
        description="Supprime définitivement un compte utilisateur (approbation obligatoire).",
        parameters=_schema(
            {
                "user_id": {"type": "integer"},
                "email": {"type": "string"},
            },
        ),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="destructive",
        requires_approval=True,
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="assign_ticket",
        description="Assigne un ticket support à un agent ou une équipe (note admin).",
        parameters=_schema(
            {
                "ticket_id": {"type": "integer"},
                "ticket_number": {"type": "string"},
                "assignee": {"type": "string"},
                "note": {"type": "string"},
            },
        ),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="write",
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="update_ticket_priority",
        description="Modifie la priorité d'un ticket support.",
        parameters=_schema(
            {
                "ticket_id": {"type": "integer"},
                "ticket_number": {"type": "string"},
                "priority": {
                    "type": "string",
                    "description": "low, medium, high, urgent, critical",
                },
            },
            required=["priority"],
        ),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="write",
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
    ToolDefinition(
        name="invite_user",
        description="Invite un nouvel utilisateur par e-mail avec lien d'activation.",
        parameters=_schema(
            {
                "email": {"type": "string"},
                "full_name": {"type": "string"},
                "role": {"type": "string", "description": "client, employe, admin"},
                "preferred_language": {"type": "string"},
            },
            required=["email"],
        ),
        allowed_roles=_ROLE_ADMIN,
        sensitivity="write",
        gpt_slugs=frozenset({"fedex-admin-ops"}),
    ),
]

_BY_NAME: dict[str, ToolDefinition] = {t.name: t for t in TOOL_DEFINITIONS}


def get_tool(name: str) -> ToolDefinition | None:
    return _BY_NAME.get(name)


def list_tools_for_gpt(gpt: GptDefinition, *, user_role: str) -> list[ToolDefinition]:
    """Outils autorisés pour ce GPT et ce rôle utilisateur."""
    role = (user_role or "client").lower()
    out: list[ToolDefinition] = []
    for tool in TOOL_DEFINITIONS:
        if gpt.slug not in tool.gpt_slugs:
            continue
        if role not in tool.allowed_roles and role != "admin":
            continue
        out.append(tool)
    return out


def gemini_tool_declarations(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    return [t.to_gemini_declaration() for t in tools]


def ollama_tool_declarations(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    """Schémas outils pour Ollama /api/chat (function calling)."""
    out: list[dict[str, Any]] = []
    for tool in tools:
        decl = tool.to_gemini_declaration()
        out.append(
            {
                "type": "function",
                "function": {
                    "name": decl["name"],
                    "description": decl.get("description", "")[:512],
                    "parameters": decl.get("parameters") or {"type": "object", "properties": {}},
                },
            }
        )
    return out
