from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import threading
import time

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db, init_db, seed_admin, SessionLocal
from app.models.user import User
from app.routes import admin, agent_missions, agent_window, auth, chat, employee, export_excel, fedex_locations, fedex_webhooks, globex_agent, help, history, notifications, reports, security_admin, settings_admin, support, system, tracking, user_notifications
from app.routes.support import admin_support_router
from app.routes.admin import dashboard_stats
from app.routes.deps import require_role
from app.schemas.admin import AdminDashboardStats

settings = get_settings()
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name, debug=settings.debug)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",
        "http://127.0.0.1:4200",
        "http://localhost:8010",
        "http://127.0.0.1:8010",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    # from app.services.client_agent.capabilities import is_phase1_chat_only
    from app.services.llm.gemini_budget import reset_global_gemini_quota

    logger.info("Client chat: Phase 3b (suivi FedEx + PDF post-réponse LLM)")
    reset_global_gemini_quota()
    init_db()
    seed_admin()
    db = SessionLocal()
    try:
        from app.services.gpt.seed import seed_gpt_platform

        seed_gpt_platform(db)
    except Exception:
        logger.exception("Échec seed GPT platform (tables KB)")
    finally:
        db.close()
    if settings.shipment_watch_enabled:
        thread = threading.Thread(target=_shipment_watch_loop, name="shipment-watch", daemon=True)
        thread.start()
        # Première vérification immédiate au démarrage
        threading.Thread(target=_run_watch_cycle_once, name="shipment-watch-initial", daemon=True).start()
    if settings.security_ids_enabled:
        threading.Thread(target=_security_ids_loop, name="security-ids", daemon=True).start()
        threading.Thread(target=_run_security_ids_once, name="security-ids-initial", daemon=True).start()
    if settings.globex_agent_enabled and settings.globex_proactive_enabled:
        threading.Thread(target=_globex_proactive_loop, name="globex-proactive", daemon=True).start()
        threading.Thread(target=_run_globex_proactive_once, name="globex-proactive-initial", daemon=True).start()
    if settings.globex_agent_enabled and settings.globex_ollama_warmup_on_start and settings.llm_enabled:
        threading.Thread(target=_globex_ollama_warmup, name="globex-ollama-warmup", daemon=True).start()
    if settings.daily_report_scheduler_enabled:
        threading.Thread(target=_daily_report_loop, name="daily-report", daemon=True).start()
        threading.Thread(target=_run_daily_report_once, name="daily-report-initial", daemon=True).start()


def _globex_ollama_warmup() -> None:
    from app.services.globex_agent.ollama_readiness import ollama_inference_ready

    try:
        ready = ollama_inference_ready(force=True)
        if ready:
            logger.info("Globex Agent : Ollama warmup OK (%s)", settings.ollama_model)
        else:
            logger.warning(
                "Globex Agent : Ollama warmup échoué — routes locales actives, "
                "lancez: ollama run %s",
                settings.ollama_model,
            )
    except Exception:
        logger.exception("Globex Agent : erreur warmup Ollama")


def _run_watch_cycle_once() -> None:
    from app.core.database import SessionLocal
    from app.services.shipment_watch_service import process_active_watches

    db = SessionLocal()
    try:
        count = process_active_watches(db)
        if count:
            logger.info("Surveillance colis (démarrage) : %s colis traités", count)
    except Exception:
        logger.exception("Erreur surveillance colis au démarrage")
    finally:
        db.close()


def _shipment_watch_loop() -> None:
    from app.core.database import SessionLocal
    from app.services.shipment_watch_service import process_active_watches

    interval = max(60, int(settings.shipment_watch_interval_seconds or 60))
    logger.info("Surveillance colis : vérification toutes les %s s", interval)
    while True:
        db = SessionLocal()
        try:
            count = process_active_watches(db)
            logger.info("Surveillance colis : cycle terminé (%s traité(s))", count)
        except Exception:
            logger.exception("Erreur boucle surveillance colis")
        finally:
            db.close()
        time.sleep(interval)


def _run_security_ids_once() -> None:
    from app.core.database import SessionLocal
    from app.services.security_ids_service import run_ai_ids_scan, run_rule_scan

    db = SessionLocal()
    try:
        rules = run_rule_scan(db)
        ai = run_ai_ids_scan(db)
        if rules or ai:
            logger.info("IDS sécurité (démarrage) : %s règle(s), %s IA", rules, ai)
    except Exception:
        logger.exception("Erreur IDS sécurité au démarrage")
    finally:
        db.close()


def _security_ids_loop() -> None:
    from app.core.database import SessionLocal
    from app.services.security_ids_service import run_ai_ids_scan, run_rule_scan

    rule_interval = max(60, int(settings.security_ids_scan_interval_seconds or 120))
    ai_interval = max(300, int(settings.security_ids_ai_interval_seconds or 900))
    logger.info("IDS sécurité : scan règles toutes les %s s, IA toutes les %s s", rule_interval, ai_interval)
    last_ai = 0.0
    while True:
        db = SessionLocal()
        try:
            rules = run_rule_scan(db)
            now = time.time()
            ai = 0
            if settings.security_ids_ai_enabled and (now - last_ai) >= ai_interval:
                ai = run_ai_ids_scan(db)
                last_ai = now
            if rules or ai:
                logger.info("IDS sécurité : %s incident(s) règles, %s incident(s) IA", rules, ai)
        except Exception:
            logger.exception("Erreur boucle IDS sécurité")
        finally:
            db.close()
        time.sleep(rule_interval)


def _run_globex_proactive_once() -> None:
    from app.services.globex_agent.proactive_scheduler import run_proactive_scan_once

    try:
        run_proactive_scan_once()
    except Exception:
        logger.exception("Erreur scan proactif Globex au démarrage")


def _globex_proactive_loop() -> None:
    from app.services.globex_agent.proactive_scheduler import proactive_scan_loop

    interval = max(60, int(settings.globex_proactive_interval_seconds or 300))
    logger.info("Globex proactive : scan SLA + dormants toutes les %s s", interval)
    proactive_scan_loop()


def _run_daily_report_once() -> None:
    from app.core.database import SessionLocal
    from app.services.client_phase8.daily_report_scheduler import process_scheduled_daily_reports

    db = SessionLocal()
    try:
        count = process_scheduled_daily_reports(db)
        if count:
            logger.info("Rapport quotidien (démarrage) : %s envoi(s)", count)
    except Exception:
        logger.exception("Erreur rapport quotidien au démarrage")
    finally:
        db.close()


def _daily_report_loop() -> None:
    from app.core.database import SessionLocal
    from app.services.client_phase8.daily_report_scheduler import process_scheduled_daily_reports

    interval = max(60, int(settings.daily_report_check_interval_seconds or 60))
    logger.info("Rapport quotidien client : vérification toutes les %s s", interval)
    while True:
        db = SessionLocal()
        try:
            count = process_scheduled_daily_reports(db)
            if count:
                logger.info("Rapport quotidien : %s envoi(s) planifié(s)", count)
        except Exception:
            logger.exception("Erreur boucle rapport quotidien")
        finally:
            db.close()
        time.sleep(interval)


@app.get("/")
def root() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(tracking.router)
app.include_router(history.router)
app.include_router(export_excel.router)
app.include_router(support.router)
app.include_router(support.router, prefix="/api")
app.include_router(user_notifications.router, prefix="/api")
app.include_router(help.router, prefix="/api")
app.include_router(admin_support_router)
app.include_router(admin_support_router, prefix="/api")
app.include_router(admin.router)
app.include_router(globex_agent.router)  # Globex OS Agent API
app.include_router(agent_window.router)
app.include_router(agent_missions.router)
app.include_router(agent_missions.approvals_router)
app.include_router(security_admin.router)
app.include_router(system.router, prefix="/admin/system")
app.include_router(system.router, prefix="/api/system")
app.include_router(settings_admin.router, prefix="/admin/settings")
app.include_router(settings_admin.router, prefix="/api/settings")
app.include_router(reports.router, prefix="/api/reports")
app.include_router(reports.router, prefix="/admin/reports")
app.include_router(reports.ai_router, prefix="/api/ai")
app.include_router(notifications.router)
app.include_router(notifications.webhooks_router)
app.include_router(fedex_webhooks.router)
app.include_router(fedex_locations.router)
app.include_router(employee.router)
app.include_router(employee.admin_employee_chat_router)


@app.get("/api/dashboard/stats", response_model=AdminDashboardStats, tags=["dashboard"])
def api_dashboard_stats(
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> AdminDashboardStats:
    return dashboard_stats(admin, db)
