"""Synthèse des résultats d'outils — locale (secours) et Gemini (réponse finale ChatGPT-like)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_MECHANICAL_REPLY = re.compile(
    r"("
    r"Utilisateurs — total|KPIs plateforme|Expéditions analysées|Voici les \d+ dernier|"
    r"Tickets : \d+|Notifications —|Conversations chat —|Résultat \w+ :|"
    r"Aucun journal d'activité|Erreur \("
    r")",
    re.I,
)

_GENERIC_ASSISTANT = re.compile(
    r"("
    r"je suis (un |votre )?assistant|i'?m your|i am your|what can i assist|how can i assist|"
    r"comment puis-je vous aider|how can i help|voici les résultats|here are the results|"
    r"je peux vous aider|i can help you|currently, i'?m in analysis mode"
    r")",
    re.I,
)

_ENGLISH_BLEED = re.compile(
    r"\b(hello!|hello |i'm your|i am your|what can i assist|how can i assist|"
    r"super admin copilot|currently, i'?m in analysis mode|you can review|"
    r"here is|here are|consider)\b",
    re.I,
)


def _generate_client_synthesis(
    prompt: str,
    *,
    system_instruction: str,
    ui_language: str = "fr",
    max_output_tokens: int = 600,
) -> str | None:
    """Synthèse client via Gemini ou Ollama selon la configuration."""
    from app.core.config import get_settings
    from app.services.llm.providers import gemini_api_key_usable

    settings = get_settings()
    if not settings.llm_enabled:
        return None

    lang = ui_language if ui_language in {"fr", "en", "ar"} else "fr"
    primary = (settings.llm_primary_provider or "ollama").strip().lower()

    if primary != "ollama" and gemini_api_key_usable():
        try:
            from app.services.llm.providers import _gemini_generate

            out = _gemini_generate(
                prompt,
                max_output_tokens=max_output_tokens,
                system_instruction=system_instruction,
                ui_language=lang,
            ).strip()
            return out or None
        except Exception:
            logger.warning("_generate_client_synthesis Gemini failed", exc_info=True)

    try:
        import httpx

        lang_label = {"fr": "français", "en": "anglais", "ar": "arabe"}.get(lang, "français")
        body = {
            "model": settings.ollama_model,
            "prompt": f"{system_instruction}\n\n{prompt}",
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_predict": min(max(max_output_tokens, 128), 800),
            },
        }
        timeout = httpx.Timeout(
            connect=8.0,
            read=max(float(settings.ollama_timeout_seconds), 60.0),
            write=20.0,
            pool=5.0,
        )
        base = settings.ollama_base_url.rstrip("/")
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(f"{base}/api/generate", json=body)
            resp.raise_for_status()
            data = resp.json()
        out = str(data.get("response") or "").strip()
        if out:
            return out
    except Exception:
        logger.warning("_generate_client_synthesis Ollama failed", exc_info=True)

    if gemini_api_key_usable() and primary == "ollama":
        try:
            from app.services.llm.providers import _gemini_generate

            out = _gemini_generate(
                prompt,
                max_output_tokens=max_output_tokens,
                system_instruction=system_instruction,
                ui_language=lang,
            ).strip()
            return out or None
        except Exception:
            logger.warning("_generate_client_synthesis Gemini fallback failed", exc_info=True)
    return None


def needs_gemini_resynthesis(reply: str, *, tools_used: list[str], lang: str = "fr") -> bool:
    """True si la réponse doit être reformulée par Gemini (dump mécanique ou ton générique)."""
    if not tools_used:
        return False
    text = (reply or "").strip()
    if not text or len(text) < 35:
        return True
    if _MECHANICAL_REPLY.search(text):
        return True
    if _GENERIC_ASSISTANT.search(text):
        return True
    if text.startswith("{") or text.startswith("["):
        return True
    if lang != "en" and _ENGLISH_BLEED.search(text):
        return True
    return False


def all_tools_failed(tool_payloads: list[dict[str, Any]]) -> bool:
    if not tool_payloads:
        return False
    for item in tool_payloads:
        payload = item.get("response") if isinstance(item.get("response"), dict) else {}
        if payload.get("status") == "error":
            continue
        if payload.get("status") in ("ok", "approval_required") or payload:
            return False
    return True


def degraded_format_tool_payload(
    tool_name: str,
    payload: dict[str, Any],
    *,
    message: str = "",
    conversation_history: str | None = None,
    ui_language: str = "fr",
    hours: int | None = None,
    ticket_status: str | None = None,
    tracking_limit: int | None = None,
) -> str:
    """
    Formatteur local — repli extrême uniquement quand Gemini est indisponible.
    Ne jamais appeler sur le chemin nominal (agent_runtime synthétise toujours via Gemini).
    """
    lang = (ui_language or "fr").lower()[:2]
    if tool_name == "analyze_users":
        return _degraded_format_users(
            payload,
            message,
            conversation_history=conversation_history,
        )
    if tool_name == "analyze_logs" and hours is not None:
        enriched = {**payload, "hours": hours}
        return _format_tool(tool_name, enriched, lang=lang) or ""
    if tool_name == "analyze_tickets" and ticket_status:
        formatted = _format_tool(tool_name, payload, lang=lang)
        if formatted and ticket_status != "open":
            return formatted.replace("Tickets :", f"Tickets ({ticket_status}) —")
        return formatted or ""
    if tool_name == "analyze_tracking" and tracking_limit is not None:
        formatted = _format_tool(tool_name, payload, lang=lang)
        if formatted:
            return formatted
    formatted = _format_tool(tool_name, payload, lang=lang)
    return formatted or ""


def _detect_users_reply_format(message: str, conversation_history: str | None = None) -> str:
    """full | names | emails — selon la question ou la relance."""
    text = (message or "").lower()
    hist = (conversation_history or "").lower() if conversation_history else ""

    if re.search(r"\b(noms?|prénoms?|prenoms?|names?)\b", text):
        return "names"
    if re.search(r"\b(emails?|mails?|adresses?)\b", text) and not re.search(r"\busers?\b", text):
        return "emails"
    if hist and len(text) < 80:
        if re.search(r"\b(que les noms|seulement les noms|juste les noms)\b", text):
            return "names"
        if re.search(r"\b(que les emails|seulement les emails)\b", text):
            return "emails"
    return "full"


def is_users_list_follow_up(message: str, conversation_history: str | None) -> bool:
    """Relance après une liste users (« je veux que les noms »)."""
    msg_l = (message or "").lower().strip()
    hist = (conversation_history or "").lower()
    if not hist or len(msg_l) > 100:
        return False
    if not re.search(
        r"\b(noms?|prénoms?|prenoms?|names?|emails?|mails?|seulement|juste|que les)\b",
        msg_l,
    ):
        return False
    return bool(
        re.search(
            r"\b(comptes utilisateurs|analyze_users|utilisateurs?|users?|affichés sur|@gmail|@globex)\b",
            hist,
        )
    )


def _degraded_format_users(
    data: dict[str, Any],
    message: str,
    *,
    conversation_history: str | None = None,
) -> str:
    total = data.get("total", 0)
    active = data.get("active", 0)
    suspended = data.get("suspended", 0)
    admins = data.get("admins", 0)
    admin_accounts = data.get("admin_accounts") or []
    users = data.get("users") or []
    msg_l = (message or "").lower()
    fmt = _detect_users_reply_format(message, conversation_history)

    wants_list = bool(
        re.search(
            r"\b(donne|donne-moi|liste|lister|affiche|montre|tous|toutes|all|show|list|users?|utilisateurs?|comptes?)\b",
            msg_l,
        )
    ) or fmt in {"names", "emails"} or is_users_list_follow_up(message, conversation_history)

    def _user_line(u: dict[str, Any]) -> str:
        name = (u.get("full_name") or "").strip() or (u.get("email") or "").split("@")[0]
        if fmt == "names":
            return f"- {name}"
        if fmt == "emails":
            return f"- {u.get('email', '—')}"
        return f"- {name} — {u['email']} (ID {u['id']}, {u['role']}, {u['status']})"

    if "admin" in msg_l and ("liste" in msg_l or "comptes" in msg_l) and not re.search(r"\busers?\b", msg_l):
        if not admin_accounts:
            return "Aucun compte administrateur trouvé en base."
        if fmt == "names":
            lines = [f"- {(a.get('full_name') or '').strip() or a['email'].split('@')[0]}" for a in admin_accounts]
        else:
            lines = [f"- {a['email']} (ID {a['id']}, statut {a['status']})" for a in admin_accounts]
        return "Comptes administrateur :\n" + "\n".join(lines)

    if users and wants_list:
        lines = [_user_line(u) for u in users]
        label = {"names": "Noms", "emails": "E-mails", "full": "Comptes utilisateurs"}[fmt]
        suffix = f" ({len(users)} affichés sur {total})" if len(users) < total and fmt == "full" else ""
        return f"{label}{suffix} :\n" + "\n".join(lines)

    if "suspendu" in msg_l:
        return f"Utilisateurs suspendus : {suspended} sur {total} comptes enregistrés."

    if "actif" in msg_l:
        return f"Utilisateurs actifs : {active} sur {total} comptes enregistrés."

    return (
        f"Vue utilisateurs — total : {total}, actifs : {active}, "
        f"suspendus : {suspended}, administrateurs : {admins}."
    )


def synthesize_admin_tool_turn(
    *,
    task: str,
    tool_payloads: list[dict[str, Any]],
    ui_language: str = "fr",
    extra_instruction: str = "",
) -> str | None:
    """Gemini reformule les résultats d'outils en réponse humaine directe (anti-hallucination)."""
    if not tool_payloads:
        return None
    from app.core.config import get_settings
    from app.services.llm.providers import gemini_api_key_usable

    settings = get_settings()
    if not settings.llm_enabled or not gemini_api_key_usable():
        return synthesize_tool_results(tool_payloads, ui_language=ui_language)

    try:
        from app.services.llm.providers import _gemini_generate
        from app.services.llm.prompts import language_lock_instruction
        from app.services.gpt.writing_style import professional_writing_for_lang

        lang = ui_language if ui_language in {"fr", "en", "ar"} else "fr"
        compact = json.dumps(tool_payloads, ensure_ascii=False, default=str)[:12000]
        prompt = (
            f"{language_lock_instruction(lang)}\n\n"
            f"{professional_writing_for_lang(lang)}\n\n"
            "Vous êtes le copilot Super Admin Globex FedEx.\n"
            "Répondez DIRECTEMENT à la question — prose professionnelle, concise, orientée action.\n"
            "INTERDIT : « Je suis un assistant », « Voici les résultats », introductions creuses.\n"
            "Utilisez UNIQUEMENT les données des outils ci-dessous — ne inventez aucun chiffre, "
            "utilisateur, colis, ticket, log ou KPI.\n"
            "Ne recopiez jamais le JSON brut : analysez et répondez comme un copilote humain.\n"
            "Pour le tracking : citez numéro + utilisateur + statut + retard éventuel.\n"
            "Pour les synthèses : listez les 3–5 points les plus importants, priorisés.\n"
            "Si une donnée manque dans les outils : « Je ne dispose pas de cette information. »\n"
            "Si tous les outils ont échoué : « L'information n'a pas pu être récupérée. »\n"
            "Pour plusieurs outils : synthétisez et priorisez (ex. top 3 ou top 5 problèmes).\n"
            f"{extra_instruction}\n"
            f"QUESTION ADMIN :\n{task[:800]}\n\n"
            f"DONNÉES OUTILS (JSON) :\n{compact}\n\n"
            "Réponse finale :"
        )
        out = _gemini_generate(prompt, max_output_tokens=1200, ui_language=lang).strip()
        return out or None
    except Exception:
        logger.warning("synthesize_admin_tool_turn failed", exc_info=True)
        return synthesize_tool_results(tool_payloads, ui_language=ui_language)


def synthesize_client_tool_turn(
    *,
    task: str,
    tool_payloads: list[dict[str, Any]],
    ui_language: str = "fr",
    preferred_name: str | None = None,
) -> str | None:
    """Reformule les résultats outil client en réponse conseiller (Gemini ou Ollama)."""
    if not tool_payloads:
        return None
    from app.core.config import get_settings
    from app.services.llm.prompts import client_tracking_system_prompt

    settings = get_settings()
    if not settings.llm_enabled:
        return synthesize_tool_results(tool_payloads, ui_language=ui_language)

    lang = ui_language if ui_language in {"fr", "en", "ar"} else "fr"
    compact = json.dumps(tool_payloads, ensure_ascii=False, default=str)[:8000]
    name = (preferred_name or "").strip()
    name_line = f"Prénom client : {name}.\n" if name else ""
    prompt = (
        f"{name_line}"
        "Vous êtes le conseiller FedEx Globex.\n"
        "Répondez DIRECTEMENT à la question du client en 3 à 6 phrases.\n"
        "Utilisez UNIQUEMENT les données outil ci-dessous — ne inventez rien.\n"
        "Si colis introuvable : citez le numéro, dites qu'il n'existe pas, proposez un numéro valide.\n"
        "Si surveillance, ticket ou export exécuté : confirmez l'action clairement.\n"
        "Si export_download ou client_export_tracking_pdf / client_generate_text_pdf a réussi (status ok, format pdf) : "
        "confirmez que le PDF est prêt et invitez à télécharger le document ci-dessous. "
        "INTERDIT de dire qu'aucun colis n'existe ou que vous ne pouvez pas générer un PDF dans ce cas. "
        "Ignorez les erreurs PDF antérieures si un export PDF a finalement réussi.\n"
        "INTERDIT : redemander le numéro déjà fourni, listes génériques FedEx, prompt injection.\n"
        f"QUESTION CLIENT :\n{task[:600]}\n\n"
        f"DONNÉES OUTIL (JSON) :\n{compact}\n\n"
        "Réponse :"
    )
    system = client_tracking_system_prompt(lang)
    out = _generate_client_synthesis(
        prompt,
        system_instruction=system,
        ui_language=lang,
        max_output_tokens=600,
    )
    if out:
        return out
    return synthesize_tool_results(tool_payloads, ui_language=ui_language)


def synthesize_client_from_fedex_context(
    *,
    task: str,
    fedex_context_json: str,
    ui_language: str = "fr",
    preferred_name: str | None = None,
) -> str | None:
    """Réponse conseiller à partir du contexte FedEx pré-chargé par le serveur."""
    from app.core.config import get_settings
    from app.services.llm.prompts import client_tracking_system_prompt

    settings = get_settings()
    if not settings.llm_enabled:
        return None

    lang = ui_language if ui_language in {"fr", "en", "ar"} else "fr"
    name = (preferred_name or "").strip()
    name_line = f"Prénom client : {name}.\n" if name else ""
    prompt = (
        f"{name_line}"
        f"Question client : {task[:600]}\n\n"
        f"Données FedEx (serveur) :\n{fedex_context_json[:6000]}\n\n"
        "Rédigez la réponse conseiller (3 à 6 phrases). "
        "Le numéro est déjà connu — ne le redemandez pas."
    )
    return _generate_client_synthesis(
        prompt,
        system_instruction=client_tracking_system_prompt(lang),
        ui_language=lang,
        max_output_tokens=600,
    )


def synthesize_copilot_reply(
    *,
    task: str,
    tool_payloads: list[dict[str, Any]],
    ui_language: str = "fr",
    fallback: str,
    extra_instruction: str = "",
) -> tuple[str, str]:
    """
    Réponse conversationnelle via Gemini — retourne (texte, provider).
    provider : gemini | degraded (repli local).
    """
    synthesized = synthesize_admin_tool_turn(
        task=task,
        tool_payloads=tool_payloads,
        ui_language=ui_language,
        extra_instruction=extra_instruction,
    )
    if synthesized:
        return synthesized, "gemini"
    return fallback, "degraded"


def synthesize_tool_results(
    tool_results: list[dict[str, Any]],
    *,
    ui_language: str = "fr",
) -> str | None:
    """Repli dégradé — formate les payloads JSON outil sans Gemini."""
    if not tool_results:
        return None

    lang = (ui_language or "fr").lower()[:2]
    parts: list[str] = []

    for item in tool_results:
        name = str(item.get("name") or "")
        payload = item.get("response") if isinstance(item.get("response"), dict) else {}
        if payload.get("status") == "error":
            err = payload.get("error") or "Erreur outil"
            parts.append(f"Erreur ({name}) : {err}")
            continue
        if payload.get("status") == "approval_required":
            parts.append(payload.get("message") or "Approbation requise.")
            continue

        formatted = _format_tool(name, payload, lang=lang)
        if formatted:
            parts.append(formatted)

    if not parts:
        return None
    return "\n\n".join(parts)


def _format_tool(name: str, payload: dict[str, Any], *, lang: str) -> str | None:
    """Formatteur mécanique local — jamais utilisé sur le chemin nominal Gemini."""
    if name == "analyze_logs":
        sample = payload.get("sample")
        if not isinstance(sample, list):
            return None
        hours = payload.get("hours", 24)
        if not sample:
            return (
                f"Aucun journal d'activité trouvé sur les {hours} dernières heures."
                if lang == "fr"
                else f"No activity logs in the last {hours} hours."
            )
        header = (
            f"Voici les {len(sample)} dernier(s) journal(aux) ({hours}h) :"
            if lang == "fr"
            else f"Last {len(sample)} log entries ({hours}h):"
        )
        lines = []
        for row in sample:
            if not isinstance(row, dict):
                continue
            ts = row.get("created_at") or "—"
            level = row.get("level") or "INFO"
            action = row.get("action") or "—"
            message = row.get("message") or ""
            lines.append(f"- {ts} [{level}] {action} — {message}")
        return header + "\n" + "\n".join(lines)

    if name == "analyze_tracking":
        sample = payload.get("sample") or []
        total = payload.get("total", len(sample))
        delayed = payload.get("delayed_count", 0)
        lines = [
            (
                f"**{len(sample)} dernière(s) opération(s) de tracking** "
                f"(sur {total} au total, {delayed} en retard) :"
                if lang == "fr"
                else f"**{len(sample)} latest tracking operation(s)** ({total} total, {delayed} delayed):"
            ),
            "",
        ]
        for row in sample[:10]:
            if not isinstance(row, dict):
                continue
            tn = row.get("tracking_number", "—")
            status = row.get("status", "—")
            ts = (row.get("created_at") or "")[:19].replace("T", " ")
            user = row.get("user_name") or row.get("user_email")
            line = f"- **{tn}** — {status}"
            if ts:
                line += f" ({ts})"
            if user:
                line += f" — utilisateur : **{user}**" if lang == "fr" else f" — user: **{user}**"
            lines.append(line)
        return "\n".join(lines)

    if name == "analyze_tickets":
        tickets = payload.get("tickets") or []
        count = payload.get("count", len(tickets))
        lines = [f"Tickets : {count}."]
        for t in tickets[:10]:
            if isinstance(t, dict):
                lines.append(f"- #{t.get('id')} [{t.get('priority')}] {t.get('subject', '')}")
        return "\n".join(lines)

    if name == "analyze_notifications":
        sample = payload.get("sample") or []
        total = payload.get("total", len(sample))
        unread = payload.get("unread_count", 0)
        if not sample:
            return (
                "Aucune notification récente pour le moment."
                if lang == "fr"
                else "No recent notifications."
            )
        header = (
            f"Notifications — {len(sample)} affichée(s) sur {total} ({unread} non lue(s)) :"
            if lang == "fr"
            else f"Notifications — showing {len(sample)} of {total} ({unread} unread):"
        )
        lines = [header]
        for row in sample[:15]:
            if isinstance(row, dict):
                tag = " [non lue]" if not row.get("is_read") and lang == "fr" else (
                    " [unread]" if not row.get("is_read") else ""
                )
                lines.append(
                    f"- {row.get('title', '—')}{tag} ({row.get('priority', 'normal')}) — "
                    f"{(row.get('message') or '')[:100]}"
                )
        return "\n".join(lines)

    if name == "analyze_conversations":
        sample = payload.get("sample") or []
        total = payload.get("total", len(sample))
        if not sample:
            return (
                "Aucune conversation client trouvée sur la plateforme."
                if lang == "fr"
                else "No client conversations found on the platform."
            )
        header = (
            f"Conversations chat — {len(sample)} affichée(s) sur {total} au total :"
            if lang == "fr"
            else f"Chat conversations — showing {len(sample)} of {total}:"
        )
        lines = [header]
        for row in sample[:25]:
            if isinstance(row, dict):
                unread = " [non lue]" if row.get("is_unread") and lang == "fr" else (
                    " [unread]" if row.get("is_unread") else ""
                )
                lines.append(
                    f"- #{row.get('session_id', '—')} — {row.get('user_name', '—')} "
                    f"({row.get('user_email', '—')}) — {row.get('title', '—')}{unread}\n"
                    f"  {row.get('category', '—')} / {row.get('status', '—')} — "
                    f"{(row.get('preview') or '')[:100]}"
                )
        if len(sample) > 25:
            lines.append(f"… +{len(sample) - 25} autre(s)")
        return "\n".join(lines)

    if name == "analyze_users":
        users = payload.get("users") or []
        total = payload.get("total", 0)
        if users:
            lines = [
                f"Utilisateurs ({len(users)} sur {total}) :",
                *[
                    f"- {(u.get('full_name') or '').strip() or (u.get('email') or '').split('@')[0]} — {u.get('email', '—')}"
                    f" (ID {u.get('id')}, {u.get('role')}, {u.get('status')})"
                    for u in users[:30]
                    if isinstance(u, dict)
                ],
            ]
            if len(users) > 30:
                lines.append(f"… +{len(users) - 30} autre(s)")
            return "\n".join(lines)
        return (
            f"Utilisateurs — total {total}, "
            f"actifs {payload.get('active', 0)}, "
            f"suspendus {payload.get('suspended', 0)}, "
            f"admins {payload.get('admins', 0)}."
        )

    if name == "get_platform_stats":
        return (
            f"KPIs plateforme — utilisateurs actifs {payload.get('active_users', '—')}, "
            f"expéditions aujourd'hui {payload.get('shipments_today', '—')}, "
            f"incidents ouverts {payload.get('open_incidents', '—')}, "
            f"requêtes FedEx {payload.get('fedex_requests_today', '—')}."
        )

    if name == "fedex_track_package":
        tn = payload.get("tracking_number") or payload.get("trackingNumber") or "—"
        if payload.get("found") is False or payload.get("status") == "not_found":
            msg = payload.get("message") or (
                "Aucun colis trouvé pour ce numéro."
                if lang == "fr"
                else "No shipment found for this tracking number."
            )
            if lang == "fr":
                return (
                    f"Je n'ai trouvé **aucun colis** correspondant au numéro **{tn}**. {msg} "
                    "Pouvez-vous vérifier le numéro ou m'en fournir un autre (12 à 14 chiffres) ?"
                )
            return f"No shipment found for **{tn}**. {msg}"
        status = payload.get("status") or payload.get("status_description") or payload.get("message")
        location = payload.get("current_location")
        eta = payload.get("estimated_delivery")
        if lang == "fr" and status:
            parts = [f"Votre colis **{tn}** est actuellement : **{status}**."]
            if location:
                parts.append(f"Dernière localisation connue : {location}.")
            if eta:
                parts.append(f"Livraison estimée : {eta}.")
            return " ".join(parts)
        if status:
            return f"Suivi **{tn}** : {status}"
        return f"Résultat suivi {tn} : {payload}"

    if name == "client_watch_shipment" and payload.get("action_executed"):
        tn = payload.get("tracking_number") or "—"
        if lang == "fr":
            return (
                f"Surveillance activée pour le colis **{tn}**. "
                "Vous recevrez une alerte en cas de changement de statut."
            )
        return f"Watch enabled for **{tn}**. You will be notified on status changes."

    if name == "client_open_support_ticket" and payload.get("action_executed"):
        ticket = payload.get("ticket_number") or payload.get("ticket_id") or "—"
        if lang == "fr":
            return f"Votre ticket support **#{ticket}** a été ouvert. Un agent vous répondra sous peu."
        return f"Support ticket **#{ticket}** has been opened."

    if name in {"client_export_tracking_excel", "client_export_tracking_pdf"} and payload.get(
        "export_download"
    ):
        fmt_label = "Excel" if "excel" in name else "PDF"
        count = payload.get("parcel_count") or 0
        if lang == "fr":
            return (
                f"Export {fmt_label} prêt — {count} colis inclus.\n"
                "Voici le fichier : (lien ci-dessous)"
            )
        return f"{fmt_label} export ready — {count} parcels.\nDownload below."

    if name == "generate_text_pdf":
        preview = str(payload.get("text_preview") or "").strip()
        if lang == "fr":
            line = f"PDF généré avec le texte demandé"
            if preview:
                line += f" : « {preview[:80]} »"
            return f"{line}.\nVoici le PDF : (lien ci-dessous)"
        return "PDF generated.\nDownload link below."

    if name == "client_generate_text_pdf":
        preview = str(payload.get("text_preview") or "").strip()
        if lang == "fr":
            line = "Votre document PDF est prêt"
            if preview:
                line += f" : « {preview[:80]} »"
            return f"{line}.\nVous pouvez le télécharger ci-dessous."
        return "Your PDF document is ready.\nYou can download it below."

    if name in {"export_activity_logs_pdf", "export_activity_logs_excel"}:
        fmt = payload.get("export_format") or ("xlsx" if "excel" in name else "pdf")
        fmt_label = "Excel" if fmt == "xlsx" else "PDF"
        file_label = "fichier" if lang == "fr" else "file"
        hours = int(payload.get("hours") or 24)
        entries = payload.get("entries", 0)
        filename = payload.get("filename") or f"activity-logs-{hours}h"
        if hours >= 24 and hours % 24 == 0:
            period = f"{hours // 24} jour(s)"
        else:
            period = f"{hours}h"
        if lang == "fr":
            return (
                f"Export {fmt_label} prêt — {entries} entrée(s) sur les {period}.\n"
                f"Voici le {file_label} : (lien ci-dessous)"
            )
        return (
            f"{fmt_label} export ready — {entries} entries over {hours}h.\n"
            f"Download: **{filename}**."
        )

    if name in {"notify_user", "send_notification"}:
        if payload.get("action_executed"):
            email = payload.get("email") or "utilisateur"
            display = email.split("@")[0].replace(".", " ").title() if "@" in str(email) else email
            return (
                f"C'est envoyé — **{display}** a reçu la notification sur son espace Globex."
                if lang == "fr"
                else f"DONE — **{display}** received the in-app notification."
            )
        err = payload.get("error")
        if err:
            return f"Je n'ai pas pu envoyer la notification : {err}" if lang == "fr" else f"NOT DONE — {err}"

    if name in {"send_client_email", "send_email"}:
        if payload.get("action_executed"):
            if payload.get("task_answer"):
                return str(payload["task_answer"])
            to = payload.get("to") or payload.get("email") or "le destinataire"
            subject = str(payload.get("subject") or "votre message")
            if lang == "fr":
                return f"C'est fait — le mail « {subject} » est parti pour **{to}**."
            return f"Done — email « {subject} » sent to **{to}**."
        err = payload.get("error")
        if err:
            return f"Je n'ai pas pu envoyer le mail : {err}" if lang == "fr" else f"Could not send email: {err}"

    if name == "scan_dormant_accounts":
        accounts = payload.get("accounts") or []
        count = int(payload.get("count") or len(accounts))
        if count == 0:
            return (
                "Aucun compte inactif détecté sur la période demandée."
                if lang == "fr"
                else "No dormant accounts found."
            )
        lines = [
            f"{count} compte(s) inactif(s) repéré(s) :"
            if lang == "fr"
            else f"{count} dormant account(s):",
        ]
        for row in accounts[:10]:
            if not isinstance(row, dict):
                continue
            label = (row.get("full_name") or row.get("email") or "—").strip()
            days = row.get("days_inactive", "?")
            lines.append(f"- **{label}** — {days}j sans activité")
        if count > 10:
            lines.append(f"… et {count - 10} autre(s)")
        return "\n".join(lines)

    if name == "scan_ticket_sla":
        breaches = payload.get("breaches") or []
        count = int(payload.get("breach_count") or len(breaches))
        if count == 0:
            return "Aucun ticket en dépassement SLA pour le moment." if lang == "fr" else "No SLA breaches."
        lines = [f"{count} ticket(s) en retard SLA :"]
        for row in breaches[:8]:
            if isinstance(row, dict):
                lines.append(
                    f"- #{row.get('ticket_id')} — retard {row.get('overdue_hours')}h "
                    f"({row.get('priority', 'medium')})"
                )
        return "\n".join(lines)

    if name.startswith("export_") and name.endswith("_pdf") and payload.get("export_download"):
        fmt = str(payload.get("export_format") or "pdf").lower()
        fmt_label = "Excel" if fmt == "xlsx" else "PDF"
        records = payload.get("records") or 0
        filename = payload.get("filename") or "export"
        mod = payload.get("module") or name.replace("export_", "").replace("_pdf", "")
        if lang == "fr":
            return (
                f"Export {fmt_label} prêt — {records} élément(s) ({mod}).\n"
                f"Voici le fichier : (lien ci-dessous)"
            )
        return f"{fmt_label} export ready — {records} items ({mod}).\nDownload below."

    if payload.get("action_executed"):
        return payload.get("task_answer") or (
            "C'est fait — l'action a bien été exécutée." if lang == "fr"
            else "Done — the action was completed."
        )

    return None
