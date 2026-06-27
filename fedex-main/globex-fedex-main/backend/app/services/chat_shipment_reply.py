"""Réponses chatbot liées au suivi, POD et événements FedEx."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any


def is_follow_up_affirmative(text: str) -> bool:
    """Réponse courte positive (« oui », « vas-y », « plus d'infos »)."""
    lowered = text.strip().lower()
    if not lowered:
        return False
    patterns = (
        r"^(oui|yes|ok|okay|d'accord|d accord|bien sûr|bien sur|vas[- ]?y|go ahead|"
        r"continue|continuer|sure|yep|yeah|النعم|نعم|أجل)\b",
        r"^(oui|yes)[,.!?\s]",
        r"\b(plus d'infos|plus de détails|plus de details|en savoir plus|tell me more|"
        r"donne[- ]?moi plus|montre[- ]?moi plus)\b",
    )
    return any(re.search(p, lowered) for p in patterns)


def is_eta_question(text: str) -> bool:
    """Question sur le délai ou la date d'arrivée / livraison."""
    lowered = text.lower()
    patterns = (
        r"dans combien de temps",
        r"combien de temps",
        r"quand (va|arrive|sera)",
        r"date de livraison",
        r"date d'arrivée",
        r"date d arrivee",
        r"heure de livraison",
        r"estimated delivery",
        r"when will (it|the package)",
        r"how long until",
        r"delivery date",
        r"arrival time",
        r"\bdélai\b",
        r"\bdelai\b",
        r"\beta\b",
        r"متى يصل",
    )
    return any(re.search(p, lowered) for p in patterns)


def is_table_request(text: str) -> bool:
    """Demande de présentation en tableau."""
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in (
            "tableau",
            "en tableau",
            "sous forme de tableau",
            "format tableau",
            "dans un tableau",
            "un table",
            "tabular",
            "as a table",
            "in a table",
            "جدول",
        )
    )


def is_session_follow_up(text: str) -> bool:
    """Question de suivi sur un colis déjà évoqué dans la conversation (sans nouveau numéro)."""
    if is_follow_up_affirmative(text):
        return True
    return any(
        (
            is_pod_request(text),
            is_delivered_question(text),
            is_recipient_question(text),
            is_where_question(text),
            is_history_question(text),
            is_details_question(text),
            is_status_question(text),
            is_events_question(text),
            is_map_request(text),
            is_eta_question(text),
            is_table_request(text),
        )
    )


INTENT_MAP_TRACKING = "map_tracking"


def is_map_request(text: str) -> bool:
    """Demande de carte géographique ou visualisation du parcours (MAP_TRACKING)."""
    lowered = text.lower()
    phrases = (
        "montre-moi la carte",
        "montre moi la carte",
        "génère une map",
        "genere une map",
        "génère-moi une map",
        "genere-moi une map",
        "génère une carte",
        "genere une carte",
        "génère-moi une carte",
        "affiche le trajet",
        "affiche la carte",
        "historique sur la carte",
        "où est passé mon colis",
        "ou est passe mon colis",
        "carte jusqu'à l'arrivée",
        "carte jusqu a l arrivee",
        "carte du trajet",
        "carte de suivi",
        "tracking map",
        "route map",
        "show me the map",
        "generate a map",
        "où est la carte",
        "ou est la carte",
        "elle est ou la carte",
        "c'est où la carte",
        "c est ou la carte",
        "montre la carte",
        "voir la carte",
        "carte",
        " map",
        "géographique",
        "geographique",
        "visualiser",
        "trajet",
        "parcours",
        "itinéraire",
        "itineraire",
        "sur une carte",
        "on a map",
        "خريطة",
    )
    return any(phrase in lowered for phrase in phrases)


def is_pod_request(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in (
            "preuve de livraison",
            "proof of delivery",
            "preuve livraison",
            "montre-moi la preuve",
            "montre moi la preuve",
            "affiche la preuve",
            "pod",
            "signature proof",
            "إثبات التسليم",
        )
    )


def is_delivered_question(text: str) -> bool:
    lowered = text.lower()
    patterns = (
        r"\b(livré|livree|delivered)\b",
        r"a[- ]t[- ]il été livré",
        r"ete livre",
        r"been delivered",
        r"est[- ]ce livré",
        r"colis livré",
        r"package delivered",
        r"هل تم التسليم",
    )
    return any(re.search(p, lowered) for p in patterns)


def is_recipient_question(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in (
            "qui a reçu",
            "qui a recu",
            "who received",
            "destinataire",
            "nom du destinataire",
            "reçu par",
            "recu par",
            "received by",
            "من استلم",
        )
    )


def is_status_question(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in (
            "statut",
            "status du colis",
            "status of",
            "quel est le statut",
            "what is the status",
            "حالة الشحنة",
        )
    ) and not is_details_question(text)


def is_details_question(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in (
            "détails",
            "details",
            "informations sur le colis",
            "package details",
            "détail du colis",
            "detail du colis",
            "تفاصيل الشحنة",
        )
    )


def is_history_question(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in (
            "historique",
            "timeline",
            "chronologie",
            "derniers événements",
            "derniers evenements",
            "dernier événement",
            "latest events",
            "last events",
            "historique des événements",
            "événements récents",
            "evenements recents",
            "scan events",
            "آخر الأحداث",
        )
    )


def is_where_question(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in (
            "où est mon colis",
            "ou est mon colis",
            "où est le colis",
            "ou est le colis",
            "where is my package",
            "where is the package",
            "localisation actuelle",
            "أين الطرد",
        )
    )


def is_events_question(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in (
            "événements visibility",
            "evenements visibility",
            "webhook",
            "visibility events",
        )
    )


def shipment_card_display_flags(intent: str) -> dict[str, bool | int]:
    """Contrôle ce que la carte colis affiche selon l'intention utilisateur."""
    show_map = intent == INTENT_MAP_TRACKING
    show_timeline = intent in (
        INTENT_MAP_TRACKING,
        "scan_history",
        "tabular_history",
        "package_details",
    )
    if intent == "tabular_history":
        max_events = 12
    elif show_timeline:
        max_events = 8
    else:
        max_events = 0
    return {
        "show_tracking_map": show_map,
        "show_timeline": show_timeline,
        "max_timeline_events": max_events,
    }


def should_attach_shipment_card(
    *,
    intent: str,
    tracking_source: str,
    pod_available: bool = False,
) -> bool:
    """
    Carte colis (UI) uniquement pour des éléments interactifs (carte Leaflet, téléchargement POD).
    Statut, lieu et ETA passent par la réponse texte — pas de carte récapitulative.
    """
    _ = tracking_source  # conservé pour compatibilité appelants
    if intent == INTENT_MAP_TRACKING:
        return True
    if intent == "proof_of_delivery" and pod_available:
        return True
    return False


def _message_is_tracking_only(message: str, tracking_number: str) -> bool:
    cleaned = message.strip()
    if tracking_number:
        cleaned = re.sub(re.escape(tracking_number), "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"[^\w\s]", " ", cleaned).strip()
    return len(cleaned) <= 12


def classify_shipment_question(message: str) -> str:
    if is_follow_up_affirmative(message):
        return "follow_up_expand"
    if is_table_request(message):
        return "tabular_history"
    if is_map_request(message):
        return INTENT_MAP_TRACKING
    if is_history_question(message):
        return "scan_history"
    if is_eta_question(message):
        return "delivery_eta"
    if is_pod_request(message):
        return "proof_of_delivery"
    if is_delivered_question(message):
        return "delivery_status"
    if is_recipient_question(message):
        return "pod_recipient"
    if is_where_question(message):
        return "where_is_package"
    if is_history_question(message):
        return "scan_history"
    if is_details_question(message):
        return "package_details"
    if is_status_question(message):
        return "status_only"
    if is_events_question(message):
        return "visibility_events"
    return "summary"


def _format_events_block(events: list[dict[str, Any]], *, limit: int = 5) -> str:
    if not events:
        return "Aucun événement enregistré pour le moment."
    lines: list[str] = []
    for ev in events[:limit]:
        at = ev.get("occurred_at") or ev.get("at") or "—"
        desc = ev.get("description") or ev.get("event_type_label") or "—"
        loc = ev.get("location") or ""
        suffix = f" ({loc})" if loc else ""
        lines.append(f"- {at} — {desc}{suffix}")
    return "\n".join(lines)


def _normalize_ui_lang(ui_language: str | None) -> str:
    lang = (ui_language or "fr").strip().lower()[:2]
    return lang if lang in ("fr", "en", "ar") else "fr"


_FEDEX_EVENT_LABELS_FR: dict[str, str] = {
    "Ready for recipient pickup": "Prêt pour retrait par le destinataire",
    "Ready for pickup": "Prêt pour retrait",
    "On FedEx vehicle for delivery": "En livraison sur le véhicule FedEx",
    "Hold at location request accepted": "Demande de retrait en point relais acceptée",
    "Arrived at FedEx location": "Arrivé en agence FedEx",
    "At local FedEx facility": "En centre de tri FedEx local",
    "Departed FedEx location": "Départ de l'agence FedEx",
    "In transit": "En transit",
    "Picked up": "Pris en charge",
    "Delivered": "Livré",
    "Shipment information sent to FedEx": "Informations d'expédition transmises à FedEx",
    "Left FedEx origin facility": "Départ du centre d'origine FedEx",
    "At destination sort facility": "En centre de tri de destination",
    "On the way": "En route",
}


def _display_event_description(raw: str | None, ui_language: str | None = None) -> str:
    text = (raw or "").strip() or "—"
    if _normalize_ui_lang(ui_language) != "fr":
        return text
    return _FEDEX_EVENT_LABELS_FR.get(text, text)


def _known_descriptions_for_events(
    events: list[dict[str, Any]],
    *,
    ui_language: str | None = None,
) -> set[str]:
    known: set[str] = set()
    for ev in events:
        raw = str(ev.get("description") or "").strip()
        if not raw:
            continue
        known.add(raw.lower())
        known.add(_display_event_description(raw, ui_language).lower())
    return known


_TABLE_HEADER_SKIP = frozenset(
    {
        "#",
        "n°",
        "no",
        "step",
        "étape",
        "etape",
        "événement",
        "evenement",
        "event",
        "lieu",
        "location",
        "date",
        "الحدث",
        "المكان",
        "التاريخ",
        "—",
        "-",
    }
)


def _format_event_datetime(raw: str | None, ui_language: str | None = None) -> str:
    if not raw:
        return "—"
    text = str(raw).strip()
    try:
        normalized = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if _normalize_ui_lang(ui_language) == "en":
            return dt.strftime("%m/%d/%Y %H:%M")
        return dt.strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return text.replace("|", "/")[:40]


def _format_scan_events_table(
    events: list[dict[str, Any]],
    *,
    limit: int = 8,
    ui_language: str | None = None,
) -> str:
    if not events:
        return "Aucun scan enregistré."
    lang = _normalize_ui_lang(ui_language)
    if lang == "en":
        col_step, col_event, col_loc, col_date = "#", "Event", "Location", "Date"
    elif lang == "ar":
        col_step, col_event, col_loc, col_date = "#", "الحدث", "المكان", "التاريخ"
    else:
        col_step, col_event, col_loc, col_date = "#", "Événement", "Lieu", "Date"
    lines = [
        f"| {col_step} | {col_event} | {col_loc} | {col_date} |",
        "| --- | --- | --- | --- |",
    ]
    for idx, ev in enumerate(events[:limit], start=1):
        raw_desc = ev.get("description") or "—"
        desc = _display_event_description(str(raw_desc), ui_language).replace("|", "/")
        loc = (ev.get("location") or "—").replace("|", "/")
        at = _format_event_datetime(ev.get("at"), ui_language)
        lines.append(f"| {idx} | {desc} | {loc} | {at} |")
    return "\n".join(lines)


def _format_scan_events(events: list[dict[str, Any]], *, limit: int = 5) -> str:
    if not events:
        return "Aucun scan enregistré."
    lines: list[str] = []
    for ev in events[:limit]:
        at = ev.get("at") or "—"
        desc = ev.get("description") or "—"
        loc = ev.get("location") or ""
        suffix = f" — {loc}" if loc else ""
        lines.append(f"- {at} : {desc}{suffix}")
    return "\n".join(lines)


def _pod_from_images(data: dict[str, Any]) -> bool:
    for img in data.get("available_images") or []:
        if isinstance(img, dict) and str(img.get("type") or "").upper() == "SIGNATURE_PROOF_OF_DELIVERY":
            return True
    return False


def build_shipment_reply(
    message: str,
    data: dict[str, Any],
    *,
    visibility_events: list[dict[str, Any]] | None = None,
    pod_info: dict[str, Any] | None = None,
    pod_available: bool = False,
) -> tuple[str, str]:
    """Retourne (reply_text, intent)."""
    intent = classify_shipment_question(message)
    if intent == "summary" and _message_is_tracking_only(message, str(data.get("tracking_number") or "")):
        intent = "summary"

    tn = data.get("tracking_number") or "—"
    status = data.get("status") or "non communiqué"
    location = data.get("current_location") or "non communiquée"
    eta = data.get("estimated_delivery") or "non communiquée"
    events = data.get("events") or []
    vis = visibility_events or []
    pod_ok = pod_available or _pod_from_images(data)

    if intent == "status_only":
        reply = (
            f"J'ai vérifié votre colis **{tn}** : il est actuellement en statut **{status}**, "
            f"avec une dernière localisation connue à **{location}**."
        )
        if eta and str(eta).lower() not in ("non communiquée", "n/a", "—", "-"):
            reply += f" La livraison est estimée pour **{eta}**."
        reply += (
            "\n\nSouhaitez-vous que je vous détaille l'historique des scans "
            "ou que je vous montre le trajet sur la carte ?"
        )
        return reply, intent

    if intent == "package_details":
        lines = [
            f"**Détails du colis {tn}**",
            f"- Statut : {status}",
            f"- Service : {data.get('service_description') or data.get('service_type') or '—'}",
            f"- Poids : {data.get('weight') or '—'}",
            f"- Dimensions : {data.get('dimensions') or '—'}",
            f"- Type : {data.get('package_type') or '—'}",
            f"- Expéditeur : {data.get('shipper') or '—'}",
            f"- Destinataire : {data.get('recipient') or '—'}",
        ]
        return "\n".join(lines), intent

    if intent == "delivery_eta":
        reply = (
            f"**Livraison estimée — colis {tn}**\n"
            f"- Date / créneau : **{eta}**\n"
            f"- Statut actuel : {status}\n"
            f"- Localisation : {location}\n\n"
            f"Souhaitez-vous voir l'historique des scans ou la carte du parcours ?"
        )
        return reply, intent

    if intent == "tabular_history":
        reply = (
            f"**Historique du colis {tn}**\n\n"
            f"{_format_scan_events_table(events, limit=8, ui_language='fr')}\n\n"
            f"Statut actuel : **{status}** — {location}\n\n"
            f"Voulez-vous la preuve de livraison ou plus de détails sur l'expéditeur / destinataire ?"
        )
        return reply, intent

    if intent == INTENT_MAP_TRACKING:
        delivered = "deliver" in (status or "").lower() or "livré" in (status or "").lower()
        reply = f"Voici la carte du trajet du colis **{tn}**."
        if delivered:
            reply += "\n\nLe colis est indiqué comme **livré** — la dernière étape est marquée sur la carte."
        else:
            reply += f"\n\nStatut actuel : **{status}** — {location}."
        reply += "\n\nSouhaitez-vous l'historique détaillé en tableau ou la preuve de livraison ?"
        return reply, intent

    if intent == "scan_history":
        reply = (
            f"**Historique des scans — {tn}**\n\n"
            f"{_format_scan_events(events, limit=8)}\n\n"
            f"Statut actuel : **{status}**"
        )
        return reply, intent

    if intent == "where_is_package":
        last = events[0] if events else None
        reply = (
            f"**Localisation du colis {tn}**\n"
            f"- Position actuelle : {location}\n"
        )
        if last:
            reply += (
                f"- Dernier événement : {last.get('description')} "
                f"({last.get('at') or '—'})"
            )
            if last.get("location"):
                reply += f"\n- Lieu du scan : {last['location']}"
        return reply, intent

    if intent == "delivery_status":
        delivered = "delivered" in (status or "").lower() or "livré" in (status or "").lower()
        if delivered:
            reply = (
                f"Oui, le colis **{tn}** est marqué **livré**.\n"
                f"- Statut : {status}\n"
                f"- Date : {data.get('actual_delivery') or pod_info.get('delivered_at') if pod_info else '—'}"
            )
            recipient = (pod_info or {}).get("received_by_name") or data.get("received_by_name")
            if recipient:
                reply += f"\n- Reçu par : {recipient}"
        else:
            reply = (
                f"Non, le colis **{tn}** n'est pas encore indiqué comme livré.\n"
                f"- Statut actuel : {status}\n"
                f"- Localisation : {location}\n"
                f"- Livraison estimée : {eta}"
            )
        return reply, intent

    if intent == "pod_recipient":
        name = (pod_info or {}).get("received_by_name") or data.get("received_by_name")
        if name:
            reply = f"Le colis **{tn}** a été reçu par **{name}**."
        elif pod_ok:
            reply = (
                f"Le colis **{tn}** est livré, mais le nom du destinataire n'est pas précisé. "
                "Consultez la preuve de livraison (PDF)."
            )
        else:
            reply = (
                f"Le colis **{tn}** n'est pas encore livré (statut : {status}). "
                "Le destinataire n'est disponible qu'après livraison."
            )
        return reply, intent

    if intent == "visibility_events":
        reply = (
            f"Événements FedEx Visibility pour **{tn}** :\n\n"
            f"{_format_events_block(vis)}\n\n"
            f"Statut actuel : **{status}** — {location}"
        )
        return reply, intent

    if intent == "proof_of_delivery":
        if pod_ok:
            reply = f"Preuve de livraison disponible pour **{tn}**.\n- Statut : {status}\n"
            if pod_info and pod_info.get("received_by_name"):
                reply += f"- Reçu par : {pod_info['received_by_name']}\n"
            reply += (
                "\nTéléchargez la **preuve de livraison (PDF)** via le bouton sous le récapitulatif du colis."
            )
        else:
            reply = (
                f"La preuve de livraison pour **{tn}** sera disponible après confirmation de livraison par FedEx.\n"
                f"- Statut actuel : {status}\n"
                f"- Localisation : {location}"
            )
        return reply, intent

    # summary — numéro seul ou demande générale
    reply = (
        f"Merci pour votre numéro de suivi. Votre colis **{tn}** est en statut **{status}**, "
        f"actuellement localisé à **{location}**."
    )
    if eta and str(eta).lower() not in ("non communiquée", "n/a", "—", "-"):
        reply += f" La livraison est estimée pour **{eta}**."
    if events:
        last = events[0]
        reply += (
            f"\n\nDernier événement enregistré : **{last.get('description') or '—'}**"
            f" ({last.get('at') or '—'})"
        )
        if last.get("location"):
            reply += f" à {last['location']}."
    reply += (
        "\n\nVoulez-vous que je vous montre l'historique complet, le trajet sur la carte, "
        "ou que je vérifie la preuve de livraison ?"
    )
    if data.get("service_commit_message"):
        reply += f"\n\nℹ️ {data['service_commit_message']}"
    return reply, intent


def validate_table_rows_match_events(
    reply: str,
    events: list[dict[str, Any]],
    *,
    ui_language: str | None = None,
) -> bool:
    """Vérifie que les lignes du tableau Markdown sont issues des événements FedEx."""
    if "| --- |" not in (reply or ""):
        return True
    if not events:
        return "| --- |" not in (reply or "")
    known_descriptions = _known_descriptions_for_events(events, ui_language=ui_language)
    known_locations = {
        str(ev.get("location") or "").strip().lower()
        for ev in events
        if ev.get("location")
    }
    for line in (reply or "").splitlines():
        if not line.strip().startswith("|") or "| --- |" in line:
            continue
        cells = [c.strip().lower() for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        if len(cells) >= 4:
            desc, loc = cells[1], cells[2]
        else:
            desc, loc = cells[0], cells[1]
        if desc in _TABLE_HEADER_SKIP:
            continue
        if desc.isdigit():
            continue
        if desc and desc not in known_descriptions:
            return False
        if loc and loc not in ("—", "-", "") and loc not in known_locations:
            return False
    return True


def format_tracking_table_hybrid(
    message: str,
    data: dict[str, Any],
    *,
    visibility_events: list[dict[str, Any]] | None = None,
    pod_info: dict[str, Any] | None = None,
    pod_available: bool = False,
    synthesize_intro: bool = True,
    ui_language: str | None = None,
    preferred_name: str | None = None,
    fedex_context_json: str | None = None,
) -> tuple[str, str, bool]:
    """
    Tableau 100 % serveur + intro LLM optionnelle.
    Retourne (reply, intent, synthesis_used).
    """
    _ = visibility_events, pod_info, pod_available
    lang = _normalize_ui_lang(ui_language)
    tn = data.get("tracking_number") or "—"
    status = data.get("status") or "non communiqué"
    location = data.get("current_location") or "non communiquée"
    events = data.get("events") or []
    table_md = _format_scan_events_table(events, limit=8, ui_language=ui_language)

    intro = ""
    synthesis_used = False
    if synthesize_intro:
        try:
            from app.services.gpt.tool_synthesis import synthesize_client_from_fedex_context

            if fedex_context_json:
                lang_label = {"fr": "français", "en": "anglais", "ar": "arabe"}.get(lang, "français")
                synthesized = synthesize_client_from_fedex_context(
                    task=(
                        f"{message}\n\n"
                        f"Consigne : l'utilisateur demande un tableau. Rédigez 2 à 3 phrases "
                        f"d'introduction personnalisées (ton conseiller, en {lang_label}). "
                        "Le tableau Markdown sera inséré automatiquement par le serveur — "
                        "ne générez AUCUN tableau, aucune ligne | --- |, ni liste de scans."
                    ),
                    fedex_context_json=fedex_context_json,
                    ui_language=lang,
                    preferred_name=preferred_name,
                )
                if synthesized:
                    intro = synthesized.strip()
                    synthesis_used = True
        except Exception:
            intro = ""

    if not intro:
        if lang == "en":
            intro = (
                f"Here is the structured tracking history for shipment **{tn}** "
                f"(current status: **{status}**)."
            )
        elif lang == "ar":
            intro = f"إليك سجل التتبع المنظم للشحنة **{tn}** (الحالة الحالية: **{status}**)."
        else:
            intro = (
                f"Voici l'historique structuré de votre colis **{tn}** "
                f"(statut actuel : **{status}**)."
            )

    if lang == "en":
        title = f"**Shipment history {tn}**"
        footer_status = f"Current status: **{status}** — {location}"
        footer_cta = (
            "Would you like the proof of delivery or more details about the shipper / recipient?"
        )
    elif lang == "ar":
        title = f"**سجل الشحنة {tn}**"
        footer_status = f"الحالة الحالية: **{status}** — {location}"
        footer_cta = "هل تريد إثبات التسليم أو مزيدًا من التفاصيل عن المرسل / المستلم؟"
    else:
        title = f"**Historique du colis {tn}**"
        footer_status = f"Statut actuel : **{status}** — {location}"
        footer_cta = (
            "Voulez-vous la preuve de livraison ou plus de détails sur l'expéditeur / destinataire ?"
        )

    if synthesis_used:
        reply = (
            f"{intro}\n\n"
            f"{table_md}\n\n"
            f"{footer_status}\n\n"
            f"{footer_cta}"
        )
    else:
        reply = (
            f"{intro}\n\n"
            f"{title}\n\n"
            f"{table_md}\n\n"
            f"{footer_status}\n\n"
            f"{footer_cta}"
        )
    if not validate_table_rows_match_events(reply, events, ui_language=ui_language):
        reply, intent = build_shipment_reply(message, data)
        return reply, intent, False
    return reply, "tabular_history", synthesis_used
