"""Réponses locales sans LLM — salutations et repli si Ollama indisponible."""

from __future__ import annotations

from typing import Any

import re

_GREETING_RE = re.compile(
    r"^(?:"
    r"(?:bonjour|salut|coucou|bonsoir|hello|hi|hey|good\s+evening|merci|thanks)"
    r"(?:\s+(?:jarvis|fedex|admin))?"
    r"|(?:hey|hi|salut|coucou)\s*,?\s*(?:jarvis|comment\s+[çc]a\s+va)"
    r")[\s!.?]*$",
    re.I,
)


def is_greeting_message(message: str) -> bool:
    return bool(_GREETING_RE.match((message or "").strip()))


def greeting_reply_text(*, lang: str, agent_mode: bool = True, message: str = "") -> str:
    low = (message or "").lower().strip()

    if lang == "en":
        if re.match(r"^good\s+evening", low):
            salutation = "Good evening"
        elif re.match(r"^(thanks|merci)", low):
            return "You're welcome! What would you like me to do on the platform?"
        else:
            salutation = "Hello"
        return (
            f"{salutation}! I'm **Jarvis**, your Globex FedEx Super Admin agent.\n\n"
            "How can I help you today — tracking, users, tickets, KPIs or exports?"
        )

    if lang == "ar":
        return (
            "مرحباً! أنا **Jarvis**، وكيل Globex FedEx للمشرف.\n\n"
            "كيف يمكنني مساعدتك على المنصة؟"
        )

    if re.match(r"^(merci|thanks)", low):
        return "Avec plaisir ! Que puis-je faire d'autre pour vous sur la plateforme ?"
    if re.match(r"^bonsoir", low):
        salutation, closing = "Bonsoir", "Que souhaitez-vous que je fasse ce soir ?"
    elif re.match(r"^(salut|coucou)", low):
        salutation, closing = "Salut", "Comment puis-je vous aider ?"
    else:
        salutation, closing = "Bonjour", "Comment puis-je vous aider ?"

    if agent_mode:
        return (
            f"{salutation} ! Je suis **Jarvis**, votre agent Super Admin Globex FedEx.\n\n"
            f"{closing}"
        )
    mode_hint = "Mode **Analyse** — posez une question sur utilisateurs, colis, tickets ou KPI."
    return (
        f"{salutation} ! Je suis **Jarvis**, assistant Super Admin Globex FedEx.\n\n"
        f"{closing}\n\n{mode_hint}"
    )


def ollama_unavailable_reply(*, lang: str) -> str:
    if lang == "en":
        return (
            "The local AI model (Ollama) is not responding. "
            "Restart Ollama or try again in a moment."
        )
    if lang == "ar":
        return (
            "نموذج الذكاء المحلي (Ollama) لا يستجيب. "
            "أعد تشغيل Ollama ثم حاول مرة أخرى."
        )
    return (
        "Le modèle local (Ollama) ne répond pas pour le moment. "
        "Les actions simples (salutations, exports directs) fonctionnent quand même."
    )


def ollama_skip_reply(*, lang: str, message: str, agent_mode: bool = True) -> str:
    """Réponse immédiate quand Ollama n'est pas prêt (évite timeout 300 s)."""
    if is_capabilities_request(message):
        return capabilities_reply_text(lang=lang, agent_mode=agent_mode)
    base = ollama_unavailable_reply(lang=lang)
    if lang == "en":
        examples = (
            "\n\nTry for example:\n"
            "- « Show open tickets »\n"
            "- « Export activity logs from the last 24 hours as PDF »"
        )
    elif lang == "ar":
        examples = ""
    else:
        examples = (
            "\n\nEssayez par exemple :\n"
            "- « Montre les tickets ouverts »\n"
            "- « Exporte les logs des dernières 24 h en PDF »"
        )
    return base + examples


_CAPABILITIES_LEGACY_RE = re.compile(
    r"\b(que\s+(peux|peut|sais|savez)[-\s]?tu\s+faire|"
    r"qu'?est[- ]ce que tu fais|tes\s+capacit|what can you do|help me)\b",
    re.I,
)

_CAPABILITIES_HELP_RE = re.compile(
    r"\b("
    r"comment\s+(?:tu\s+)?(?:peux|puis).{0,16}aider|"
    r"comment\s+m[''\u2019]?\s*aider|"
    r"en\s+quoi\s+(?:tu\s+)?(?:peux|puis)\s+(?:m[''\u2019]?\s*aider|aider)|"
    r"how\s+can\s+you\s+help|"
    r"what\s+(?:can\s+you\s+help|do\s+you\s+do)\s+(?:me\s+)?(?:with)?"
    r")\b",
    re.I,
)

# Alias rétrocompatibilité
_CAPABILITIES_RE = _CAPABILITIES_LEGACY_RE


def is_capabilities_request(message: str) -> bool:
    """Détection unifiée — questions sur capacités / aide (sans Ollama)."""
    text = (message or "").strip()
    if not text:
        return False
    return bool(_CAPABILITIES_LEGACY_RE.search(text) or _CAPABILITIES_HELP_RE.search(text))


def is_capabilities_message(message: str) -> bool:
    return is_capabilities_request(message)


def capabilities_reply_text(*, lang: str, agent_mode: bool = True) -> str:
    if lang == "en":
        return (
            "I'm **Jarvis**, your Globex FedEx admin agent.\n\n"
            "I can track shipments, list users, handle support tickets, "
            "review activity logs, summarize KPIs and generate PDF/Excel exports.\n\n"
            "Example: « Export activity logs from the last 24 hours as PDF »."
        )
    if agent_mode:
        return (
            "Je suis **Jarvis**, votre agent admin Globex FedEx.\n\n"
            "Je peux suivre les colis, lister les utilisateurs, traiter les tickets, "
            "consulter les journaux, synthétiser les KPI et générer des exports PDF/Excel.\n\n"
            "Exemple : « Exporte les logs des dernières 24 h en PDF »."
        )
    return (
        "Je suis **Jarvis**, votre assistant admin Globex FedEx.\n\n"
        "Je peux suivre les colis, lister les utilisateurs, traiter les tickets, "
        "consulter les journaux, synthétiser les KPI et générer des exports PDF/Excel.\n\n"
        "Mode **Analyse** : consultation seule. Activez le mode Agent pour agir."
    )


def naturalize_tool_reply(
    tool_payloads: list[dict[str, Any]],
    *,
    message: str,
    lang: str,
) -> str | None:
    """Réponse naturelle sans noms d'outils techniques (repli si Ollama indisponible)."""
    if not tool_payloads:
        return None

    item = tool_payloads[-1]
    name = str(item.get("name") or "")
    payload = item.get("response") if isinstance(item.get("response"), dict) else {}

    if payload.get("status") == "approval_required":
        params = payload.get("parameters") or {}
        hours = int(params.get("hours") or 24)
        if "log" in name or name.startswith("export_activity"):
            if lang == "en":
                return (
                    f"I can prepare a **PDF report** of activity logs for the last **{hours} hours**. "
                    "Shall I go ahead?"
                )
            return (
                f"Très bien — je peux préparer un **rapport PDF** des journaux "
                f"sur les **{hours} dernières heures**. Je lance l'export ?"
            )
        if lang == "en":
            return "This action needs your confirmation before I run it. Approve below?"
        return "Cette action nécessite votre validation avant exécution. Vous confirmez ?"

    if name in {"export_activity_logs_pdf", "export_activity_logs_excel"}:
        hours = int(payload.get("hours") or 24)
        entries = int(payload.get("entries") or 0)
        fmt = "Excel" if "excel" in name else "PDF"
        if hours >= 24 and hours % 24 == 0:
            period = f"{hours // 24} jour(s)" if lang == "fr" else f"{hours // 24} day(s)"
        else:
            period = f"{hours} h" if lang == "fr" else f"{hours}h"
        if lang == "en":
            return (
                f"Done — your **{fmt} log report** for the last **{period}** is ready "
                f"({entries} entries). Download it below."
            )
        return (
            f"C'est prêt — voici votre **rapport {fmt}** des journaux sur les **{period}** "
            f"({entries} entrées). Téléchargez-le via le lien ci-dessous."
        )

    if payload.get("export_download") or payload.get("action_executed"):
        fname = str(payload.get("filename") or "export")
        if lang == "en":
            return f"Your file **{fname}** is ready — use the download link below."
        return f"Voilà — le fichier **{fname}** est prêt. Utilisez le lien de téléchargement ci-dessous."

    return None
