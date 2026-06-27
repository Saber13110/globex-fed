"""Résolution des relances courtes (« ce numéro », « ce colis ») via l'historique."""

from __future__ import annotations

import re

from app.services.gpt.knowledge_service import extract_fedex_tracking_numbers


_FOLLOW_UP_RE = re.compile(
    r"\b("
    r"ce\s+num[eé]ro|ce\s+colis|cette?\s+num[eé]ro|celui|celle|"
    r"ces\s+infos|ces\s+informations|sous\s+forme\s+de|le\s+tableau|"
    r"dont\s+on\s+parlait|comme\s+avant|"
    r"les|ceux|ceux-ci|cela|it|this|that|those|them|"
    r"existe|valid|valide|toujours|encore|m[êe]me"
    r")\b",
    re.I,
)


def expand_follow_up_message(message: str, conversation_history: str | None) -> str:
    """
    Enrichit un message court de relance avec les entités de l'historique récent.
    Ex. « est ce que ce numero existe ? » → inclut le dernier numéro de suivi discuté.
    """
    msg = (message or "").strip()
    hist = (conversation_history or "").strip()
    if not msg or not hist:
        return msg
    if len(msg) > 140 and not _FOLLOW_UP_RE.search(msg):
        return msg
    if not _FOLLOW_UP_RE.search(msg):
        return msg

    tracking = extract_fedex_tracking_numbers(hist)
    filenames = re.findall(r"[\w\-]+\.(?:xlsx|xls|pdf|csv|docx)", hist, re.I)

    hints: list[str] = []
    if tracking:
        hints.append(f"dernier numéro de suivi discuté : {tracking[-1]}")
        if len(tracking) > 1:
            hints.append(f"autres numéros dans la conversation : {', '.join(tracking[-5:])}")
    if filenames:
        hints.append(f"fichier(s) mentionné(s) : {', '.join(dict.fromkeys(filenames[-3:]))}")

    if not hints:
        hints.append("reportez-vous au dernier échange Copilot/Administrateur ci-dessus")

    return (
        f"{msg}\n\n"
        f"[Relance conversation — résoudre « ce/cette/les » avec CONVERSATION_HISTORY : "
        f"{'; '.join(hints)}. Ne redemandez pas un numéro déjà fourni.]"
    )
