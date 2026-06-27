"""Moteur de raisonnement général — AI Command Center admin.

Distinction READ (mode Analyse) vs ACTION (mode Agent uniquement).
Gemini choisit les modules et outils ; le serveur filtre les permissions.
"""

from __future__ import annotations

from app.services.gpt.tool_types import ToolDefinition

# Modules métier du centre de commande
ADMIN_MODULES: dict[str, dict[str, object]] = {
    "dashboard": {
        "label": "Tableau de bord / KPI",
        "read_tools": ("get_platform_stats", "analyze_reports"),
    },
    "users": {
        "label": "Utilisateurs et comptes",
        "read_tools": ("analyze_users",),
        "action_tools": ("suspend_user", "reactivate_user", "export_users_pdf"),
    },
    "tracking": {
        "label": "Expéditions et suivi FedEx",
        "read_tools": (
            "analyze_tracking",
            "fedex_track_package",
            "find_fedex_location",
        ),
        "action_tools": ("export_tracking_pdf", "export_tracking_status_pdf"),
    },
    "logs": {
        "label": "Journaux d'activité",
        "read_tools": ("analyze_logs",),
        "action_tools": ("export_activity_logs_pdf", "export_activity_logs_excel"),
    },
    "notifications": {
        "label": "Notifications admin",
        "read_tools": ("analyze_notifications",),
        "action_tools": ("send_notification", "export_notifications_pdf"),
    },
    "tickets": {
        "label": "Tickets support",
        "read_tools": ("analyze_tickets",),
        "action_tools": ("create_ticket", "export_tickets_pdf"),
    },
    "conversations": {
        "label": "Conversations chat",
        "read_tools": ("analyze_conversations",),
        "action_tools": ("export_conversations_pdf",),
    },
    "reports": {
        "label": "Rapports et synthèses",
        "read_tools": ("analyze_reports", "get_platform_stats"),
    },
    "security": {
        "label": "Sécurité et incidents",
        "read_tools": ("analyze_security", "analyze_notifications"),
        "action_tools": ("run_security_scan",),
    },
    "knowledge": {
        "label": "Base de connaissances GPT",
        "read_tools": ("search_knowledge", "list_knowledge_documents"),
    },
    "missions": {
        "label": "Agent Missions",
        "action_tools": ("create_agent_mission",),
    },
}

READ_TOOL_NAMES: frozenset[str] = frozenset(
    name
    for mod in ADMIN_MODULES.values()
    for name in mod.get("read_tools", ())
)

ACTION_TOOL_NAMES: frozenset[str] = frozenset(
    name
    for mod in ADMIN_MODULES.values()
    for name in mod.get("action_tools", ())
)


def is_read_tool(defn: ToolDefinition) -> bool:
    """Outil lecture seule — autorisé en mode Analyse."""
    return defn.sensitivity == "read" and not defn.requires_approval


def is_action_tool(defn: ToolDefinition) -> bool:
    """Outil avec effet de bord ou approbation — mode Agent uniquement."""
    return not is_read_tool(defn)


def filter_tools_for_admin_mode(
    tools: list[ToolDefinition],
    *,
    analysis_mode: bool,
) -> list[ToolDefinition]:
    if not analysis_mode:
        return tools
    return [t for t in tools if is_read_tool(t)]


def action_requires_agent_mode_message(lang: str) -> str:
    if lang == "en":
        return (
            "This action requires **Agent mode** (toggle in the copilot header). "
            "Analysis mode can only read data — it cannot execute exports or account changes."
        )
    if lang == "ar":
        return "يتطلب هذا الإجراء **وضع الوكيل** — وضع التحليل للقراءة فقط."
    return (
        "Cette action nécessite le **mode Agent** (bouton dans l'en-tête du copilot). "
        "Le mode Analyse permet uniquement de consulter les données, pas d'exécuter "
        "d'exports, de suspensions de compte ou d'autres actions."
    )


def no_data_access_message(lang: str) -> str:
    if lang == "en":
        return "I don't have access to that data at the moment."
    if lang == "ar":
        return "لا يمكنني الوصول إلى هذه البيانات حالياً."
    return "Je n'ai pas accès à cette donnée pour le moment."


def build_admin_reasoning_prompt(*, analysis_mode: bool, lang: str) -> str:
    """Consignes générales de raisonnement — pas de règle par question."""
    mode_label = "ANALYSE (lecture seule)" if analysis_mode else "AGENT (lecture + actions)"
    read_list = ", ".join(sorted(READ_TOOL_NAMES))
    action_list = ", ".join(sorted(ACTION_TOOL_NAMES))

    modules_block = "\n".join(
        f"- **{key}** ({meta['label']}) : lecture={meta.get('read_tools', ())}"
        + (f" ; actions={meta.get('action_tools', ())}" if meta.get("action_tools") else "")
        for key, meta in ADMIN_MODULES.items()
    )

    analysis_rules = ""
    if analysis_mode:
        analysis_rules = f"""
MODE ACTUEL : {mode_label}
OUTILS DISPONIBLES (lecture uniquement) : {read_list}
OUTILS ACTION (NON exposés — mode Agent requis) : {action_list}

Si l'utilisateur demande une action (export PDF/Excel, suspension compte, notification, mission…) :
→ n'inventez pas le résultat ;
→ expliquez qu'il faut activer le **mode Agent** ;
→ vous pouvez d'abord afficher les données en lecture si pertinent.

Relances (« en PDF », « sous forme Excel », « les mêmes ») :
→ lisez CONVERSATION_HISTORY pour comprendre le sujet ;
→ en mode Analyse : proposez les données en texte ou invitez au mode Agent pour l'export.
"""
    else:
        analysis_rules = f"""
MODE ACTUEL : {mode_label}
OUTILS LECTURE : {read_list}
OUTILS ACTION : {action_list}

Actions sensibles (suspend_user, reactivate_user) : approbation admin requise.
Exports logs : export_activity_logs_pdf / export_activity_logs_excel.
"""

    lang_rule = (
        "Répondez ENTIÈREMENT en français."
        if lang == "fr"
        else "Respond ENTIRELY in English."
        if lang == "en"
        else "أجب بالعربية الفصحى بالكامل."
    )

    return f"""
MOTEUR DE RAISONNEMENT — AI COMMAND CENTER
{analysis_rules}

MODULES PLATEFORME :
{modules_block}

PIPELINE OBLIGATOIRE (toute reformulation) :
1. Comprendre l'intention (donnée, synthèse, action, relance, salutation).
2. Identifier le ou les module(s) concernés.
3. Appeler le(s) READ TOOL(s) nécessaires — plusieurs outils autorisés pour les synthèses transversales.
4. Attendre les résultats réels ; ne jamais inventer users, colis, logs, tickets, KPI, documents.
5. Reformuler en prose humaine, directe, professionnelle ({lang_rule}).

SALUTATIONS (bonjour, bonsoir, merci) :
- Aucun outil requis.
- Réponse courte : « Bonsoir 👋 Que souhaitez-vous vérifier ce soir ? »
- INTERDIT : présentation longue, « Je suis le Copilot Super Admin », liste de capacités.

ANTI-HALLUCINATION :
- Aucune donnée récupérée → « {no_data_access_message(lang)} »
- Outil en erreur → expliquer brièvement, proposer une alternative.
- Ne jamais répondre « Je suis un assistant FedEx » pour une question admin plateforme.
- Ne jamais citer « prompt injection » pour une question métier légitime.

EXEMPLES DE RAISONNEMENT (logique, pas de regex) :
- « Donne les 5 notifications » → analyze_notifications (afficher en texte), PAS d'export PDF.
- « Génère-les en PDF » (après une liste) → export du module précédent, PAS les logs par défaut.
- Derniers tracking + utilisateur → analyze_tracking (inclut user_email/user_name).
- Comptes admin → analyze_users(role=admin) — pas de réponse tracking client.
- Problèmes critiques / priorités du jour → get_platform_stats + analyze_logs + analyze_notifications
  + analyze_tracking + analyze_tickets → synthèse numérotée priorisée.
- Activité récente / choses à surveiller → analyze_notifications + analyze_logs + get_platform_stats.
- Documents base connaissances → list_knowledge_documents ou search_knowledge.
- Sécurité / incidents → analyze_security.
- Rapport global → analyze_reports ou multi-outils dashboard.

STYLE : copilote admin humain — données d'abord, pas d'introduction générique sur vos capacités.
"""
