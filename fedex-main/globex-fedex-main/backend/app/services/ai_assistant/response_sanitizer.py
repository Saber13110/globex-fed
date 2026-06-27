"""Sanitisation des réponses — interdit JSON brut et messages vides."""

from __future__ import annotations

import ast
import json
import re
from typing import Any

_RAW_DICT_RE = re.compile(r"^\s*[\{\[].*[\}\]]\s*$", re.S)
_UNAVAILABLE_RE = re.compile(
    r"\b(copilot indisponible|none|null|result:\s*$|\{\s*\})\b",
    re.I,
)


def looks_like_raw_data(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if _RAW_DICT_RE.match(t):
        return True
    if t.startswith("{'") or t.startswith('{"status"'):
        return True
    return False


def format_payload_as_french(payload: dict[str, Any], *, tool_hint: str = "") -> str:
    """Transforme un payload outil en texte admin lisible."""
    if not payload:
        return "Aucune donnée disponible pour le moment."

    lines: list[str] = []

    if "incidents" in payload or "security" in tool_hint:
        count = payload.get("count") or payload.get("total") or len(payload.get("incidents") or [])
        critical = payload.get("critical_count") or payload.get("critical") or 0
        high = payload.get("high_count") or payload.get("elevated") or 0
        lines.append(f"**{count}** incident(s) de sécurité ouvert(s).")
        if critical or high:
            lines.append(f"- {critical} critique(s)")
            lines.append(f"- {high} élevé(s)")
        lines.append("\n**Action recommandée :** surveiller les tentatives de prompt injection et les accès suspects.")

    elif "tickets" in payload:
        count = payload.get("count", len(payload.get("tickets") or []))
        lines.append(f"**{count}** ticket(s) support ouvert(s).")
        for t in (payload.get("tickets") or [])[:5]:
            if isinstance(t, dict):
                lines.append(f"- #{t.get('id', '?')} — {t.get('subject', 'Sans objet')[:80]} ({t.get('status', '?')})")

    elif "users" in payload or "active" in payload:
        total = payload.get("total") or payload.get("count") or len(payload.get("users") or [])
        active = payload.get("active")
        if active is not None:
            lines.append(f"**{active}** utilisateur(s) actif(s) sur **{total}** au total.")
        else:
            lines.append(f"**{total}** utilisateur(s) enregistré(s).")

    elif payload.get("tracking_number"):
        tn = payload["tracking_number"]
        status = payload.get("status") or payload.get("fedex_status") or "—"
        sender = payload.get("user_name") or payload.get("sender") or payload.get("shipper")
        lines.append(f"**Colis {tn}** — Statut : **{status}**")
        if sender:
            lines.append(f"Expéditeur / utilisateur lié : **{sender}**")

    elif payload.get("total") is not None or payload.get("count") is not None:
        n = payload.get("total", payload.get("count"))
        label = tool_hint.replace("_", " ") if tool_hint else "éléments"
        lines.append(f"**{n}** {label}.")

    else:
        for key in ("message", "summary", "description"):
            if payload.get(key):
                lines.append(str(payload[key]))
                break
        if not lines:
            snippet = json.dumps(payload, ensure_ascii=False, default=str)[:400]
            lines.append(f"Données disponibles : {snippet}")

    return "\n".join(lines)


def format_tool_result_for_user(
    result: dict[str, Any] | str | None,
    *,
    intent: str = "",
    language: str = "fr",
    tool_name: str = "",
) -> str:
    """Transforme un résultat technique en réponse lisible — jamais de dict brut."""
    if isinstance(result, str):
        return sanitize_reply(result)

    payload = result or {}
    if payload.get("export_ready") or payload.get("export_download"):
        count = payload.get("count") or payload.get("records") or 0
        filename = payload.get("filename") or (payload.get("export_download") or {}).get("filename") or "export.pdf"
        module = intent.replace("export_", "").replace("_pdf", "") or tool_name.replace("export_", "").replace("_pdf", "")
        if language == "fr":
            return f"PDF généré avec succès : **{count}** {module} exporté(s).\nTéléchargez : **{filename}**"
        return f"PDF generated: **{count}** {module} exported.\nDownload: **{filename}**"

    text = format_payload_as_french(payload, tool_hint=tool_name or intent)
    return sanitize_reply(text)


def sanitize_reply(reply: str, *, tool_payloads: list[dict[str, Any]] | None = None) -> str:
    """Nettoie une réponse avant envoi à l'utilisateur."""
    text = (reply or "").strip()

    if not text or text.lower() in {"none", "null", "{}"}:
        if tool_payloads:
            p = tool_payloads[-1]
            return format_payload_as_french(
                p.get("response") or {},
                tool_hint=p.get("name") or "",
            )
        return "Je n'ai pas pu formuler une réponse. Réessayez ou précisez votre demande."

    if _UNAVAILABLE_RE.search(text) and tool_payloads:
        p = tool_payloads[-1]
        formatted = format_payload_as_french(p.get("response") or {}, tool_hint=p.get("name") or "")
        if formatted and "Aucune donnée" not in formatted:
            return formatted

    if looks_like_raw_data(text):
        try:
            data = json.loads(text.replace("'", '"'))
        except json.JSONDecodeError:
            try:
                data = ast.literal_eval(text)
            except (SyntaxError, ValueError):
                data = None
        if isinstance(data, dict):
            hint = ""
            if tool_payloads:
                hint = tool_payloads[-1].get("name") or ""
            return format_payload_as_french(data, tool_hint=hint)

    if text.lower().startswith("result:"):
        return sanitize_reply(text[7:].strip(), tool_payloads=tool_payloads)

    return text
