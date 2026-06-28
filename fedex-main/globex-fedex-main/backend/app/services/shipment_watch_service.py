"""Surveillance automatique des colis + notifications e-mail (Visibility intégrée)."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.fedex_visibility_event import FedexVisibilityEvent
from app.models.shipment_cache import ShipmentCache
from app.models.shipment_watch import ShipmentWatch
from app.models.user import User
from app.services import fedex_service
from app.services.email_service import is_email_configured, send_email
from app.services.fedex_sandbox_whitelist import (
    FedExSandboxWhitelistError,
    is_fedex_sandbox,
    is_whitelisted_tracking_number,
    sandbox_whitelist_applies,
)
from app.services.fedex_visibility_service import (
    map_fedex_scan_to_visibility_type,
    sync_visibility_from_tracking,
)
from app.services.shipment_cache_service import upsert_shipment_cache
from app.services.user_notification_service import create_user_notification

logger = logging.getLogger(__name__)

ALERT_ALL = "all"
ALERT_DELIVERED = "delivered"
ALERT_DELAY = "delay"
ALERT_OUT_FOR_DELIVERY = "out_for_delivery"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _event_matches_alert(event_type: str, description: str, alert_type: str) -> bool:
    et = (event_type or "").upper()
    desc = (description or "").lower()
    if alert_type == ALERT_ALL:
        return True
    if alert_type == ALERT_DELIVERED:
        return et == "DELIVERED" or ("deliver" in desc and "exception" not in desc)
    if alert_type == ALERT_OUT_FOR_DELIVERY:
        return et == "OUT_FOR_DELIVERY" or "out for delivery" in desc or "en livraison" in desc
    if alert_type == ALERT_DELAY:
        return et in {"DELIVERY_EXCEPTION", "CLEARANCE_DELAY", "SHIPMENT_EXCEPTION"} or any(
            k in desc for k in ("delay", "retard", "exception", "hold", "late")
        )
    return True


def _max_visibility_event_id(db: Session, tracking_number: str) -> int:
    tn = tracking_number.strip().upper()
    return int(
        db.scalar(
            select(func.max(FedexVisibilityEvent.id)).where(
                FedexVisibilityEvent.tracking_number == tn
            )
        )
        or 0
    )


def baseline_watch_visibility_cursor(db: Session, watch: ShipmentWatch) -> None:
    """Évite d'alerter pour l'historique déjà connu à l'inscription."""
    watch.last_visibility_event_id = _max_visibility_event_id(db, watch.tracking_number)


def _extract_scans_chronological(shipment_data: dict[str, Any]) -> list[dict[str, Any]]:
    scans: list[dict[str, Any]] = []
    raw = shipment_data.get("raw")
    if isinstance(raw, dict):
        output = raw.get("output") or {}
        if isinstance(output, dict):
            for block in output.get("completeTrackResults") or []:
                if not isinstance(block, dict):
                    continue
                for tr in block.get("trackResults") or []:
                    if isinstance(tr, dict) and isinstance(tr.get("scanEvents"), list):
                        scans.extend([s for s in tr["scanEvents"] if isinstance(s, dict)])
    if not scans:
        for ev in shipment_data.get("events") or []:
            if isinstance(ev, dict):
                scans.append(ev)
    # Plus ancien → plus récent pour la simulation sandbox
    scans.reverse()
    return scans


def advance_sandbox_watch_simulation(
    db: Session,
    watch: ShipmentWatch,
    shipment_data: dict[str, Any],
) -> FedexVisibilityEvent | None:
    """Sandbox : injecte le prochain scan FedEx comme nouvel événement Visibility (démo)."""
    settings = get_settings()
    if not settings.fedex_visibility_simulation_enabled or not is_fedex_sandbox():
        return None

    scans = _extract_scans_chronological(shipment_data)
    if not scans:
        return None

    cursor = int(watch.sandbox_sim_cursor or 0)
    if cursor >= len(scans):
        cursor = 0
    scan = scans[cursor]
    desc = str(
        scan.get("eventDescription")
        or scan.get("description")
        or scan.get("derivedStatus")
        or "Mise à jour de suivi"
    )
    event_code = scan.get("eventType")
    event_type = map_fedex_scan_to_visibility_type(
        str(event_code) if event_code else None,
        desc,
    )
    loc = None
    scan_loc = scan.get("scanLocation")
    if isinstance(scan_loc, dict):
        parts = [p for p in [scan_loc.get("city"), scan_loc.get("countryName")] if p]
        loc = ", ".join(parts) if parts else None
    elif isinstance(scan.get("location"), str):
        loc = scan.get("location")

    tn = watch.tracking_number.strip().upper()
    # Empreinte unique à chaque cycle (sandbox : statuts réels inchangés, on injecte un scan simulé).
    fp = hashlib.sha256(
        f"watch-sim|{watch.id}|{tn}|{cursor}|{_now().isoformat()}".encode()
    ).hexdigest()

    row = FedexVisibilityEvent(
        tracking_number=tn,
        event_type=event_type,
        event_code=str(event_code) if event_code else None,
        description=desc,
        location=loc,
        occurred_at=_now(),
        source="fedex_watch_simulator",
        fingerprint=fp,
        raw_payload_json=json.dumps(scan, ensure_ascii=False, default=str),
    )
    db.add(row)
    db.flush()
    watch.sandbox_sim_cursor = cursor + 1

    cache = db.scalar(select(ShipmentCache).where(ShipmentCache.tracking_number == tn))
    if cache is None:
        db.add(
            ShipmentCache(
                tracking_number=tn,
                raw_response_json=json.dumps({"source": "fedex_watch_simulator"}),
                last_status=desc,
                last_location=loc,
            )
        )
    else:
        cache.last_status = desc
        if loc:
            cache.last_location = loc

    logger.info(
        "Simulation Visibility sandbox — %s étape %s/%s : %s",
        tn,
        cursor + 1,
        len(scans),
        desc[:80],
    )
    return row


def _sandbox_watch_demo_mode() -> bool:
    """En sandbox, la simulation injecte des événements — on garde la surveillance active."""
    settings = get_settings()
    return bool(settings.fedex_visibility_simulation_enabled and is_fedex_sandbox())


def _watch_email_limit_reached(watch: ShipmentWatch) -> bool:
    cap = watch.max_email_updates
    if cap is None:
        return False
    return int(watch.email_updates_sent or 0) >= int(cap)


def _try_send_watch_update_email(
    user: User,
    watch: ShipmentWatch,
    *,
    subject: str,
    body: str,
) -> bool:
    if not watch.notify_email or not is_email_configured():
        return False
    if _watch_email_limit_reached(watch):
        return False
    to = (user.email or "").strip()
    if not to:
        return False
    try:
        if send_email(to=to, subject=subject, body_text=body):
            watch.email_updates_sent = int(watch.email_updates_sent or 0) + 1
            logger.info(
                "E-mail alerte surveillance envoyé à %s pour %s (%s/%s)",
                to,
                watch.tracking_number,
                watch.email_updates_sent,
                watch.max_email_updates if watch.max_email_updates is not None else "∞",
            )
            return True
    except Exception:
        logger.exception("Échec email alerte watch %s", watch.tracking_number)
    return False


def upsert_watch(
    db: Session,
    *,
    user_id: int,
    tracking_number: str,
    alert_type: str = ALERT_ALL,
    notify_email: bool = True,
    notify_in_app: bool = True,
    max_email_updates: int | None = None,
) -> ShipmentWatch:
    tn = tracking_number.strip()
    if sandbox_whitelist_applies() and not is_whitelisted_tracking_number(tn):
        raise FedExSandboxWhitelistError(tn)
    row = db.scalar(
        select(ShipmentWatch)
        .where(
            ShipmentWatch.user_id == user_id,
            ShipmentWatch.tracking_number == tn,
        )
        .order_by(ShipmentWatch.id.desc())
    )
    if row is None:
        row = ShipmentWatch(
            user_id=user_id,
            tracking_number=tn,
            alert_type=alert_type or ALERT_ALL,
            notify_email=notify_email,
            notify_in_app=notify_in_app,
            max_email_updates=max_email_updates,
            email_updates_sent=0,
        )
        db.add(row)
    else:
        row.is_active = True
        row.alert_type = alert_type or row.alert_type
        row.notify_email = notify_email
        row.notify_in_app = notify_in_app
        row.max_email_updates = max_email_updates
        row.email_updates_sent = 0
    db.flush()
    return row


def finalize_watch_subscription(db: Session, watch: ShipmentWatch, shipment_data: dict[str, Any]) -> None:
    """Sync Visibility + curseur initial (ignore l'historique déjà connu)."""
    sync_visibility_from_tracking(db, shipment_data, source="watch_subscribe", commit=False)
    baseline_watch_visibility_cursor(db, watch)
    db.flush()


def send_watch_confirmation_email(user: User, watch: ShipmentWatch) -> bool:
    if not watch.notify_email or not is_email_configured():
        return False
    to = (user.email or "").strip()
    if not to:
        return False
    alert_labels = {
        ALERT_ALL: "à chaque changement de statut",
        ALERT_DELIVERED: "uniquement à la livraison",
        ALERT_DELAY: "en cas de retard ou exception",
        ALERT_OUT_FOR_DELIVERY: "quand le colis est en livraison",
    }
    when = alert_labels.get(watch.alert_type, alert_labels[ALERT_ALL])
    limit_line = ""
    if watch.max_email_updates is not None:
        limit_line = f"\nNombre maximum de mails d'avancement : {watch.max_email_updates}.\n"
    subject = f"[Globex FedEx] Surveillance activée — {watch.tracking_number}"
    body = (
        f"Bonjour {user.full_name or ''},\n\n"
        f"La surveillance automatique est active pour le colis {watch.tracking_number}.\n"
        f"Vous serez alerté(e) {when}.\n"
        f"{limit_line}"
        f"Les mises à jour passent par le flux Visibilité intégrée FedEx.\n\n"
        f"— Votre agent FedEx Globex"
    )
    try:
        return send_email(to=to, subject=subject, body_text=body)
    except Exception:
        logger.exception("Échec email confirmation surveillance %s", watch.tracking_number)
        return False


def activate_client_shipment_watch(
    db: Session,
    *,
    user: User,
    tracking_number: str,
    alert_type: str = ALERT_ALL,
    notify_email: bool = True,
    notify_in_app: bool = True,
    max_email_updates: int | None = None,
) -> dict[str, Any]:
    """
    Inscription surveillance client : FedEx sync, 1er scan sandbox simulé, e-mail confirmation.
  """
    tn = tracking_number.strip()
    watch = upsert_watch(
        db,
        user_id=user.id,
        tracking_number=tn,
        alert_type=alert_type,
        notify_email=notify_email,
        notify_in_app=notify_in_app,
        max_email_updates=max_email_updates,
    )
    notified_before = watch.last_notified_status
    data = fedex_service.get_shipment(tn)
    upsert_shipment_cache(db, data)
    finalize_watch_subscription(db, watch, data)
    process_single_watch(db, watch)
    confirmation_sent = send_watch_confirmation_email(user, watch) if notify_email else False
    alert_sent = bool(
        watch.last_notified_status
        and watch.last_notified_status != notified_before
    )
    return {
        "watch": watch,
        "tracking_number": tn,
        "confirmation_sent": confirmation_sent,
        "alert_sent": alert_sent,
        "status": data.get("status"),
        "location": data.get("current_location"),
    }


def notify_watch_visibility_event(
    db: Session,
    *,
    user: User,
    watch: ShipmentWatch,
    event: FedexVisibilityEvent,
) -> None:
    if not _event_matches_alert(event.event_type, event.description, watch.alert_type):
        return

    loc_suffix = f" — {event.location}" if event.location else ""
    label = event.description or event.event_type
    message = f"{label}{loc_suffix}"

    if watch.notify_in_app:
        create_user_notification(
            db,
            user_id=user.id,
            type="tracking_update",
            title="Mise à jour colis surveillé",
            message=f"{watch.tracking_number} : {message}",
            related_tracking_number=watch.tracking_number,
            link="/notifications",
        )
        logger.info(
            "Notification in-app surveillance — user=%s colis=%s : %s",
            user.id,
            watch.tracking_number,
            label[:80],
        )

    if watch.notify_email and is_email_configured():
        subject = f"[Globex FedEx] Colis {watch.tracking_number} — {label}"
        body = (
            f"Bonjour {user.full_name or ''},\n\n"
            f"Votre colis {watch.tracking_number} a été mis à jour "
            f"(Visibilité intégrée FedEx) :\n"
            f"Événement : {event.event_type}\n"
            f"Détail : {message}\n\n"
            f"Consultez votre espace Globex FedEx.\n\n"
            f"— Agent FedEx Globex"
        )
        _try_send_watch_update_email(user, watch, subject=subject, body=body)

    watch.last_notified_status = label
    watch.last_status = label


def _process_new_visibility_events(
    db: Session,
    *,
    user: User,
    watch: ShipmentWatch,
) -> int:
    if watch.last_visibility_event_id is None:
        baseline_watch_visibility_cursor(db, watch)
    after_id = int(watch.last_visibility_event_id or 0)
    tn = watch.tracking_number.strip().upper()
    rows = list(
        db.scalars(
            select(FedexVisibilityEvent)
            .where(
                FedexVisibilityEvent.tracking_number == tn,
                FedexVisibilityEvent.id > after_id,
            )
            .order_by(FedexVisibilityEvent.id.asc())
        ).all()
    )
    notified = 0
    for event in rows:
        notify_watch_visibility_event(db, user=user, watch=watch, event=event)
        watch.last_visibility_event_id = event.id
        notified += 1
        if event.event_type == "DELIVERED" and not _sandbox_watch_demo_mode():
            watch.is_active = False
    return notified


def _deactivate_watch_invalid_tracking(
    db: Session,
    *,
    user: User,
    watch: ShipmentWatch,
    reason: str,
) -> None:
    watch.is_active = False
    msg = (
        f"La surveillance du colis {watch.tracking_number} a été arrêtée : {reason}"
    )
    if watch.notify_in_app:
        create_user_notification(
            db,
            user_id=user.id,
            type="tracking_update",
            title="Surveillance colis interrompue",
            message=msg,
            related_tracking_number=watch.tracking_number,
            link="/notifications",
        )
    if watch.notify_email and is_email_configured() and user.email:
        try:
            send_email(
                to=user.email,
                subject=f"[Globex FedEx] Surveillance arrêtée — {watch.tracking_number}",
                body_text=f"Bonjour {user.full_name or ''},\n\n{msg}\n\n— Agent FedEx Globex",
            )
        except Exception:
            logger.exception("Échec email arrêt surveillance %s", watch.tracking_number)


def process_single_watch(db: Session, watch: ShipmentWatch) -> bool:
    user = db.get(User, watch.user_id)
    if user is None or not watch.is_active:
        return False
    try:
        data = fedex_service.get_shipment(watch.tracking_number)
    except FedExSandboxWhitelistError:
        logger.warning(
            "Numéro hors whitelist sandbox pour surveillance %s — désactivation",
            watch.tracking_number,
        )
        _deactivate_watch_invalid_tracking(
            db,
            user=user,
            watch=watch,
            reason="ce numéro n'est pas autorisé en environnement FedEx sandbox.",
        )
        return False
    except Exception:
        logger.exception("FedEx indisponible pour surveillance %s", watch.tracking_number)
        return False

    upsert_shipment_cache(db, data)
    sync_visibility_from_tracking(db, data, source="watch_sync", commit=False)
    advance_sandbox_watch_simulation(db, watch, data)

    new_status = str(data.get("status") or "")
    location = str(data.get("current_location") or "")
    watch.last_status = new_status or watch.last_status

    notified = _process_new_visibility_events(db, user=user, watch=watch)
    if notified:
        logger.info("Watch %s : %s notification(s) Visibility", watch.tracking_number, notified)
        return True

    previous = watch.last_notified_status
    if (
        new_status
        and new_status != previous
        and _event_matches_alert("IN_TRANSIT", new_status, watch.alert_type)
    ):
        if watch.notify_in_app:
            create_user_notification(
                db,
                user_id=user.id,
                type="tracking_update",
                title="Mise à jour colis surveillé",
                message=f"{watch.tracking_number} : {new_status} — {location}".strip(" —"),
                related_tracking_number=watch.tracking_number,
                link="/notifications",
            )
        _try_send_watch_update_email(
            user,
            watch,
            subject=f"[Globex FedEx] Colis {watch.tracking_number} — {new_status}",
            body=(
                f"Statut FedEx : {new_status}\nLieu : {location}\n\n— Agent FedEx Globex"
            ),
        )
        watch.last_notified_status = new_status

    if (
        new_status
        and "deliver" in new_status.lower()
        and "exception" not in new_status.lower()
        and not _sandbox_watch_demo_mode()
    ):
        watch.is_active = False
    return True


def deactivate_user_watches(
    db: Session,
    *,
    user_id: int,
    tracking_number: str | None = None,
    stop_email: bool = False,
    stop_app: bool = False,
    stop_all: bool = False,
) -> list[ShipmentWatch]:
    """Arrête ou réduit les alertes de surveillance pour un ou plusieurs colis."""
    stmt = select(ShipmentWatch).where(
        ShipmentWatch.user_id == user_id,
        ShipmentWatch.is_active.is_(True),
    )
    if tracking_number:
        stmt = stmt.where(ShipmentWatch.tracking_number == tracking_number.strip())
    watches = list(db.scalars(stmt).all())
    for watch in watches:
        if stop_all:
            watch.is_active = False
        else:
            if stop_email:
                watch.notify_email = False
            if stop_app:
                watch.notify_in_app = False
            if not watch.notify_email and not watch.notify_in_app:
                watch.is_active = False
    db.flush()
    return watches


def process_active_watches(db: Session, *, limit: int = 50) -> int:
    watches = list(
        db.scalars(
            select(ShipmentWatch)
            .where(ShipmentWatch.is_active.is_(True))
            .order_by(ShipmentWatch.updated_at.asc())
            .limit(limit)
        ).all()
    )
    if not watches:
        logger.debug("Surveillance colis : aucun abonnement actif")
        return 0
    processed = 0
    for watch in watches:
        try:
            if process_single_watch(db, watch):
                processed += 1
        except Exception:
            logger.exception("Erreur traitement watch %s", watch.tracking_number)
    db.commit()
    return processed


def notify_watchers_for_visibility_event(
    db: Session,
    event: FedexVisibilityEvent,
    *,
    commit: bool = False,
) -> int:
    """Appelé à l'ingestion webhook/simulateur — notifie les abonnements actifs."""
    watches = list(
        db.scalars(
            select(ShipmentWatch).where(
                ShipmentWatch.tracking_number == event.tracking_number,
                ShipmentWatch.is_active.is_(True),
            )
        ).all()
    )
    count = 0
    for watch in watches:
        if watch.last_visibility_event_id and event.id <= watch.last_visibility_event_id:
            continue
        user = db.get(User, watch.user_id)
        if user is None:
            continue
        notify_watch_visibility_event(db, user=user, watch=watch, event=event)
        watch.last_visibility_event_id = event.id
        count += 1
    if count:
        if commit:
            db.commit()
    return count
