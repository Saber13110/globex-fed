"""Classification d'intention GPT — scores, règles et journalisation."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from app.services.llm.tracking_extract import extract_tracking_number

logger = logging.getLogger(__name__)

INTENT_ADMIN_TRACKING = "admin_tracking"
INTENT_CAPABILITIES = "capabilities"
INTENT_ADMIN_AGENTS = "admin_agents"
INTENT_ADMIN_USERS = "admin_users"
INTENT_ADMIN_TICKETS = "admin_tickets"
INTENT_ADMIN_NOTIFICATIONS = "admin_notifications"
INTENT_ADMIN_CONVERSATIONS = "admin_conversations"
INTENT_ADMIN_LOGS = "admin_logs"
INTENT_KNOWLEDGE = "knowledge_query"
INTENT_ADMIN_QUERY = "admin_query"
INTENT_TRACK = "track_package"
INTENT_GENERAL = "general_question"
INTENT_SECURITY = "security_blocked"

_CAPABILITY_TRIGGERS = (
    "que peux",
    "que peut tu",
    "peut tu faire",
    "peut-tu faire",
    "qu'est-ce que tu",
    "qu'est ce que tu",
    "qu est ce que tu",
    "qu'est que tu peux",
    "qu est que tu peux",
    "quest ce que tu",
    "what can you",
    "what else",
    "capabilities",
    "capacités",
    "capacites",
    "tu fais quoi",
    "vous pouvez faire",
    "peux tu faire",
    "peux-tu faire",
    "ce que tu peux",
    "what you can do",
    "donne ce que tu peux",
    "dis ce que tu peux",
    "faire aussi",
    "autre chose",
    "autres choses",
    "sert a quoi",
    "sert à quoi",
    "quels outils",
    "quel outil",
    "outils as-tu",
    "outils avez-vous",
    "outils disponibles",
    "liste des outils",
    "liste outils",
    "tools do you",
    "what tools",
    "at your disposal",
    "à ta disposition",
    "a ta disposition",
)

_CAPABILITY_PATTERN = re.compile(
    r"(?:"
    r"(?:que\s+)?(?:peux|peut|pouvez|pourrais)[-\s]?(?:tu|vous)\s+"
    r"(?:(?:encore|aussi)\s+)?(?:faire|fais|fait)\b"
    r"|(?:ce\s+que\s+tu\s+(?:peux|peut)|what\s+(?:else\s+)?can\s+you)"
    r"|(?:tu|vous)\s+fais\s+quoi"
    r"|(?:autre(?:s)?\s+choses?|faire\s+aussi|what\s+else)"
    r"|(?:capabilities|capacit[eé]s?)"
    r"|(?:quels?\s+(?:sont\s+)?(?:les\s+)?(?:outils?|tools?))"
    r"|(?:outils?\s+(?:as[-\s]?tu|avez|disponibles|[àa]\s+ta\s+disposition))"
    r"|(?:tools?\s+(?:do\s+you\s+have|available|at\s+your\s+disposition))"
    r")",
    re.I,
)

# Agents copilot (logs, tracking, users…) — distinct des capacités générales
_ADMIN_AGENTS_PATTERN = re.compile(
    r"(?:"
    r"\bagents?\b.{0,70}\b(r[oô]les?|chacun|chaque|présents?|present|existants?|disponibles?)\b"
    r"|\b(r[oô]les?)\b.{0,50}\b(chacun|chaque|agents?)\b"
    r"|\bagents?\b.{0,50}\bsert(?:ent)?\s+[aà]\s+quoi\b"
    r"|\b(quels?|quelles?)\s+(sont\s+)?(les\s+)?agents?\b"
    r")",
    re.I,
)

_KNOWLEDGE_TRIGGERS = (
    "base de connaissances",
    "base de connaissance",
    "knowledge base",
    "documents dans",
    "document ajouté",
    "document ajoute",
    "dernier document",
    "dans ta base",
    "dans votre base",
    "fichiers indexés",
    "fichiers indexes",
    "quels documents",
    "liste des documents",
    "ne trouves pas",
    "ne trouve pas",
    "pas d'information en base",
    "pas trouvé en base",
)

_ADMIN_CONVERSATIONS_RULES: list[tuple[str, re.Pattern[str], int]] = [
    (
        "conv_all_users",
        re.compile(
            r"\b(conversations?|discussions?|chats?|échanges?|echanges?|sessions?)\b"
            r".{0,50}\b(tous|all|utilisateurs?|users?|clients?)\b",
            re.I,
        ),
        98,
    ),
    (
        "want_conversations",
        re.compile(
            r"\b(veux|voudrais|souhaite|donne|donne-moi|liste|affiche|montre)\b"
            r".{0,60}\b(conversations?|discussions?|chats?|échanges?|echanges?)\b",
            re.I,
        ),
        96,
    ),
    (
        "conversations_list",
        re.compile(
            r"\b(conversations?|discussions?|chats?)\b.{0,40}"
            r"\b(récentes?|recentes?|plateforme|globex|clients?)\b",
            re.I,
        ),
        88,
    ),
]

_ADMIN_TRACKING_RULES: list[tuple[str, re.Pattern[str], int]] = [
    (
        "tracking_with_users",
        re.compile(
            r"\b(tracking|exp[eé]ditions?|colis|shipments?)\b.{0,60}"
            r"\b(par\s+quel|par\s+quelle|utilisateur|utilisateurs?|users?|comptes?)\b",
            re.I,
        ),
        98,
    ),
    (
        "tracking_last_ops",
        re.compile(
            r"\b(donne|liste|affiche|montre|derni[eè]res?|operations?|op[eé]rations?)\b"
            r".{0,50}\b(tracking|exp[eé]ditions?|colis|shipments?|livraisons?)\b",
            re.I,
        ),
        94,
    ),
    (
        "tracking_ops_simple",
        re.compile(
            r"\b(tracking|exp[eé]ditions?|colis|shipments?)\b.{0,40}"
            r"\b(derni[eè]res?|recentes?|r[eé]centes?|liste|historique)\b",
            re.I,
        ),
        90,
    ),
    (
        "tracking_domain",
        re.compile(
            r"\b(tracking|exp[eé]ditions?|colis en retard|retards? fedex|shipments?)\b",
            re.I,
        ),
        82,
    ),
]

_ADMIN_USERS_RULES: list[tuple[str, re.Pattern[str], int]] = [
    (
        "want_give_users",
        re.compile(
            r"\b(veux|voudrais|souhaite|donne|donne-moi|give|show|list|liste|affiche|montre)\b"
            r".{0,60}\b(users?|utilisateurs?|comptes?)\b",
            re.I,
        ),
        95,
    ),
    (
        "all_users_en",
        re.compile(
            r"(donne|liste|list|show|give|all|tous|toutes).{0,30}\b(users?|accounts?)\b",
            re.I,
        ),
        90,
    ),
    (
        "all_users_fr",
        re.compile(
            r"(donne|liste|affiche|montre|tous|toutes).{0,30}\b(utilisateurs?|comptes?|users?)\b",
            re.I,
        ),
        90,
    ),
    (
        "admin_accounts_list",
        re.compile(
            r"(liste|lister|affiche|montre|donne).{0,40}(comptes?\s+)?admin",
            re.I,
        ),
        90,
    ),
    (
        "admin_accounts_list_fr",
        re.compile(r"comptes?\s+admin(istrateur)?s?", re.I),
        85,
    ),
    (
        "active_users_count",
        re.compile(r"(combien|nombre).{0,30}(utilisateurs?|comptes?).{0,20}actifs?", re.I),
        88,
    ),
    (
        "suspended_users",
        re.compile(
            r"(quels?|liste|combien|utilisateurs?).{0,40}(suspendu|suspendus|bloqu)",
            re.I,
        ),
        88,
    ),
    (
        "users_analysis",
        re.compile(
            r"\b(utilisateurs?|comptes?|employés?|employes?)\b.{0,40}"
            r"\b(actifs?|suspendus?|inactifs?|admin|rôle|role)\b",
            re.I,
        ),
        70,
    ),
]


_ADMIN_TICKETS_RULES: list[tuple[str, re.Pattern[str], int]] = [
    (
        "open_tickets",
        re.compile(r"(ticket|tickets).{0,40}(ouvert|ouverts|encore\s+ouvert|open)", re.I),
        92,
    ),
    (
        "tickets_request",
        re.compile(r"(donne|liste|affiche|montre|quels?).{0,35}(ticket|tickets)", re.I),
        88,
    ),
    (
        "support_open",
        re.compile(r"\b(support|plainte|demande).{0,35}(ouvert|ouverts|pending)", re.I),
        82,
    ),
]


_ADMIN_NOTIFICATIONS_RULES: list[tuple[str, re.Pattern[str], int]] = [
    (
        "last_n_notifications",
        re.compile(
            r"\b(dernier|dernières|dernieres|\d+)\b.{0,35}\b(notifications?|notifs?|alertes?)\b",
            re.I,
        ),
        94,
    ),
    (
        "notifications_list",
        re.compile(
            r"(donne|liste|affiche|montre|combien|quelles?|résume|resume|donne-moi).{0,50}"
            r"\b(notifications?|notifs?|alertes?)\b",
            re.I,
        ),
        93,
    ),
    (
        "notifications_filters",
        re.compile(
            r"\b(notifications?|notifs?)\b.{0,40}\b(non lues?|critiques?|récentes?|recentes?|du jour|importantes?)\b",
            re.I,
        ),
        90,
    ),
    (
        "notifications_keyword",
        re.compile(r"\b(notifications?|notifs?)\b", re.I),
        78,
    ),
]


_ADMIN_LOGS_RULES: list[tuple[str, re.Pattern[str], int]] = [
    (
        "logs_pdf_export",
        re.compile(
            r"(export|exporter|générer|generer|télécharger|telecharger|format|pdf|excel|xlsx|csv).{0,40}(logs?|journaux|activit)",
            re.I,
        ),
        92,
    ),
    (
        "logs_pdf_export_fr",
        re.compile(
            r"(logs?|journaux).{0,40}(pdf|excel|xlsx|csv|export|télécharger|telecharger|format)",
            re.I,
        ),
        92,
    ),
    (
        "logs_request",
        re.compile(
            r"(?:"
            r"(?:donne|liste|affiche|montre|analyse).{0,40}(?:logs?|journaux|24h|24\s*h|activit)"
            r"|\b(?:logs?|journaux)\b.{0,40}(?:24h|24\s*h|dernier|dernières|dernieres|heure|activit|aujourd)"
            r")",
            re.I,
        ),
        88,
    ),
    (
        "logs_simple",
        re.compile(r"\b(logs?|journaux)\b.{0,30}\b(dernier|dernières|dernieres|24h|aujourd)\b", re.I),
        85,
    ),
]


@dataclass
class IntentClassification:
    intent: str
    score: int
    rules: list[str] = field(default_factory=list)
    gpt_slug: str = ""
    message_preview: str = ""

    def log(self) -> None:
        logger.info(
            "Intent GPT slug=%s intent=%s score=%s rules=%s msg=%r",
            self.gpt_slug,
            self.intent,
            self.score,
            ",".join(self.rules) or "-",
            self.message_preview[:80],
        )


def classify_intent(message: str, gpt_slug: str) -> IntentClassification:
    text = (message or "").lower().strip()
    rules: list[str] = []
    score = 0
    intent = INTENT_GENERAL

    if gpt_slug.startswith("fedex-admin") and _ADMIN_AGENTS_PATTERN.search(text):
        result = IntentClassification(
            intent=INTENT_ADMIN_AGENTS,
            score=97,
            rules=["admin_agents:regex"],
            gpt_slug=gpt_slug,
            message_preview=message or "",
        )
        result.log()
        return result

    if gpt_slug.startswith("fedex-admin") and _CAPABILITY_PATTERN.search(text):
        result = IntentClassification(
            intent=INTENT_CAPABILITIES,
            score=96,
            rules=["capability:regex"],
            gpt_slug=gpt_slug,
            message_preview=message or "",
        )
        result.log()
        return result

    for trigger in _CAPABILITY_TRIGGERS:
        if trigger in text:
            rules.append(f"capability:{trigger}")
            return IntentClassification(
                intent=INTENT_CAPABILITIES,
                score=95,
                rules=rules,
                gpt_slug=gpt_slug,
                message_preview=message or "",
            )

    if gpt_slug.startswith("fedex-admin"):
        ticket_score = 0
        ticket_rules: list[str] = []
        for rule_name, pattern, weight in _ADMIN_TICKETS_RULES:
            if pattern.search(text):
                ticket_rules.append(rule_name)
                ticket_score = max(ticket_score, weight)
        if ticket_score >= 70:
            result = IntentClassification(
                intent=INTENT_ADMIN_TICKETS,
                score=ticket_score,
                rules=ticket_rules,
                gpt_slug=gpt_slug,
                message_preview=message or "",
            )
            result.log()
            return result

        conv_score = 0
        conv_rules: list[str] = []
        for rule_name, pattern, weight in _ADMIN_CONVERSATIONS_RULES:
            if pattern.search(text):
                conv_rules.append(rule_name)
                conv_score = max(conv_score, weight)
        if conv_score >= 70:
            result = IntentClassification(
                intent=INTENT_ADMIN_CONVERSATIONS,
                score=conv_score,
                rules=conv_rules,
                gpt_slug=gpt_slug,
                message_preview=message or "",
            )
            result.log()
            return result

        tracking_score = 0
        tracking_rules: list[str] = []
        for rule_name, pattern, weight in _ADMIN_TRACKING_RULES:
            if pattern.search(text):
                tracking_rules.append(rule_name)
                tracking_score = max(tracking_score, weight)
        if tracking_score >= 70:
            result = IntentClassification(
                intent=INTENT_ADMIN_TRACKING,
                score=tracking_score,
                rules=tracking_rules,
                gpt_slug=gpt_slug,
                message_preview=message or "",
            )
            result.log()
            return result

        users_score = 0
        users_rules: list[str] = []
        for rule_name, pattern, weight in _ADMIN_USERS_RULES:
            if pattern.search(text):
                users_rules.append(rule_name)
                users_score = max(users_score, weight)
        if users_score >= 70:
            result = IntentClassification(
                intent=INTENT_ADMIN_USERS,
                score=users_score,
                rules=users_rules,
                gpt_slug=gpt_slug,
                message_preview=message or "",
            )
            result.log()
            return result

        notif_score = 0
        notif_rules: list[str] = []
        for rule_name, pattern, weight in _ADMIN_NOTIFICATIONS_RULES:
            if pattern.search(text):
                notif_rules.append(rule_name)
                notif_score = max(notif_score, weight)
        if notif_score >= 70:
            result = IntentClassification(
                intent=INTENT_ADMIN_NOTIFICATIONS,
                score=notif_score,
                rules=notif_rules,
                gpt_slug=gpt_slug,
                message_preview=message or "",
            )
            result.log()
            return result

        logs_score = 0
        logs_rules: list[str] = []
        for rule_name, pattern, weight in _ADMIN_LOGS_RULES:
            if pattern.search(text):
                logs_rules.append(rule_name)
                logs_score = max(logs_score, weight)
        if logs_score >= 70:
            result = IntentClassification(
                intent=INTENT_ADMIN_LOGS,
                score=logs_score,
                rules=logs_rules,
                gpt_slug=gpt_slug,
                message_preview=message or "",
            )
            result.log()
            return result

        for trigger in _KNOWLEDGE_TRIGGERS:
            if trigger in text:
                rules.append(f"knowledge:{trigger}")
                result = IntentClassification(
                    intent=INTENT_KNOWLEDGE,
                    score=85,
                    rules=rules,
                    gpt_slug=gpt_slug,
                    message_preview=message or "",
                )
                result.log()
                return result

        result = IntentClassification(
            intent=INTENT_ADMIN_QUERY,
            score=60,
            rules=["admin_default"],
            gpt_slug=gpt_slug,
            message_preview=message or "",
        )
        result.log()
        return result

    tracking = extract_tracking_number(message)
    if tracking:
        rules.append("tracking_number_extracted")
        result = IntentClassification(
            intent=INTENT_TRACK,
            score=80,
            rules=rules,
            gpt_slug=gpt_slug,
            message_preview=message or "",
        )
        result.log()
        return result

    for trigger in _KNOWLEDGE_TRIGGERS:
        if trigger in text:
            rules.append(f"knowledge:{trigger}")
            result = IntentClassification(
                intent=INTENT_KNOWLEDGE,
                score=75,
                rules=rules,
                gpt_slug=gpt_slug,
                message_preview=message or "",
            )
            result.log()
            return result

    result = IntentClassification(
        intent=INTENT_GENERAL,
        score=40,
        rules=rules or ["general_default"],
        gpt_slug=gpt_slug,
        message_preview=message or "",
    )
    result.log()
    return result
