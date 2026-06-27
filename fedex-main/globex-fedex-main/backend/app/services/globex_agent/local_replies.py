"""Réponses locales sans LLM — salutations et repli si Ollama indisponible."""

from __future__ import annotations

from typing import Any

import re

_GREETING_RE = re.compile(
    r"^(bonjour|salut|coucou|bonsoir|hello|hi|hey|good\s+evening|merci|thanks)[\s!.?]*$",
    re.I,
)


def is_greeting_message(message: str) -> bool:
    return bool(_GREETING_RE.match((message or "").strip()))


def greeting_reply_text(*, lang: str, agent_mode: bool = False, message: str = "") -> str:
    low = (message or "").lower().strip()
    mode_hint = (
        "Mode **Agent** actif — je peux exécuter des actions (export, notifications…)."
        if agent_mode
        else "Mode **Analyse** — posez une question sur utilisateurs, colis, tickets ou KPI."
    )

    if lang == "en":
        if re.match(r"^good\s+evening", low):
            salutation = "Good evening"
        elif re.match(r"^(thanks|merci)", low):
            return "You're welcome! What would you like to check on the platform?"
        else:
            salutation = "Hello"
        return (
            f"{salutation}! I'm **Fedex-v0**, Globex FedEx Super Admin assistant.\n\n"
            f"{mode_hint}"
        )

    if lang == "ar":
        return (
            "مرحباً! أنا **Fedex-v0**، مساعد Globex FedEx للمشرف.\n\n"
            "كيف يمكنني مساعدتك على المنصة؟"
        )

    if re.match(r"^(merci|thanks)", low):
        return "Avec plaisir ! Que puis-je faire d'autre pour vous sur la plateforme ?"
    if re.match(r"^bonsoir", low):
        salutation, closing = "Bonsoir", "Que souhaitez-vous vérifier ce soir ?"
    elif re.match(r"^(salut|coucou)", low):
        salutation, closing = "Salut", "Comment puis-je vous aider ?"
    else:
        salutation, closing = "Bonjour", "Que puis-je vérifier pour vous sur la plateforme ?"

    return (
        f"{salutation} ! Je suis **Fedex-v0**, assistant Super Admin Globex FedEx.\n\n"
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


_CAPABILITIES_RE = re.compile(
    r"\b(que\s+(peux|peut|sais|savez)[-\s]?tu\s+faire|"
    r"qu'?est[- ]ce que tu fais|tes\s+capacit|what can you do|help me)\b",
    re.I,
)


def is_capabilities_message(message: str) -> bool:
    return bool(_CAPABILITIES_RE.search((message or "").strip()))


def capabilities_reply_text(*, lang: str, agent_mode: bool = False) -> str:
    mode = (
        "Mode **Agent** : j'exécute exports, notifications, suspensions (avec validation si sensible)."
        if agent_mode
        else "Mode **Analyse** : consultation des données. Activez le mode Agent pour agir."
    )
    if lang == "en":
        return (
            "I'm **Fedex-v0**, your Globex FedEx admin copilot.\n\n"
            "I can help with shipments, users, support tickets, activity logs, KPIs and exports.\n\n"
            f"{mode}"
        )
    return (
        "Je suis **Fedex-v0**, votre assistant admin Globex FedEx.\n\n"
        "Je peux suivre les colis, lister les utilisateurs, traiter les tickets, "
        "consulter les journaux, synthétiser les KPI et générer des exports PDF/Excel.\n\n"
        f"{mode}\n\n"
        "Exemple : « Exporte les logs des dernières 24 h en PDF »."
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
