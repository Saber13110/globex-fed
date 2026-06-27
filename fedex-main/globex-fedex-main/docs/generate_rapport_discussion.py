#!/usr/bin/env python3
"""Génère le document Word/PDF consolidant la discussion PFE Globex FedEx."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT_DIR = Path(__file__).resolve().parent
DOCX_PATH = OUT_DIR / "RAPPORT_PFE_GLOBEX_FEDEX_DISCUSSION.docx"
PDF_PATH = OUT_DIR / "RAPPORT_PFE_GLOBEX_FEDEX_DISCUSSION.pdf"


def add_title_page(doc: Document) -> None:
    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = t.add_run("RAPPORT DE PROJET DE FIN D'ÉTUDES\n")
    r.bold = True
    r.font.size = Pt(18)
    r2 = t.add_run("\nGlobex FedEx Chatbot — Plateforme conversationnelle logistique\n")
    r2.font.size = Pt(14)
    r3 = t.add_run("\nDocument consolidé — Analyse technique, réalisation, tests et annexes\n")
    r3.font.size = Pt(12)
    r3.italic = True
    d = doc.add_paragraph(f"\nGénéré le {date.today().strftime('%d/%m/%Y')}\n")
    d.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_page_break()


def h1(doc: Document, text: str) -> None:
    doc.add_heading(text, level=1)


def h2(doc: Document, text: str) -> None:
    doc.add_heading(text, level=2)


def h3(doc: Document, text: str) -> None:
    doc.add_heading(text, level=3)


def p(doc: Document, text: str) -> None:
    doc.add_paragraph(text)


def code(doc: Document, text: str) -> None:
    para = doc.add_paragraph()
    run = para.add_run(text)
    run.font.name = "Consolas"
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)


def table(doc: Document, headers: list[str], rows: list[list[str]]) -> None:
    t = doc.add_table(rows=1 + len(rows), cols=len(headers))
    t.style = "Table Grid"
    for i, h in enumerate(headers):
        t.rows[0].cells[i].text = h
    for ri, row in enumerate(rows):
        for ci, cell in enumerate(row):
            t.rows[ri + 1].cells[ci].text = cell
    doc.add_paragraph("")


def build_docx() -> Path:
    doc = Document()
    add_title_page(doc)

    h1(doc, "Table des matières (sommaire)")
    for item in [
        "1. Contexte et stack technique",
        "2. Chapitre Réalisation (texte académique)",
        "3. Architecture et diagrammes Mermaid",
        "4. Inventaire frontend Angular",
        "5. Modules administrateur",
        "6. Plan de tests",
        "7. Difficultés techniques et solutions",
        "8. Captures d'écran recommandées",
        "9. Guide de démarrage et soutenance",
        "10. Synthèse réalisé / partiel / non réalisé",
        "11. Annexes",
    ]:
        p(doc, item)
    doc.add_page_break()

    # --- 1 Contexte ---
    h1(doc, "1. Contexte et stack technique")
    p(
        doc,
        "Le projet Globex FedEx Chatbot v2.4.0 est une plateforme three-tier : Angular 17 (port 4200), "
        "FastAPI (port 8000) et PostgreSQL (globex_fedex). Un sidecar Jarvis-OS (port 8013) complète "
        "l'écosystème sans remplacer le backend métier.",
    )
    table(
        doc,
        ["Couche", "Technologies"],
        [
            ["Frontend", "Angular 17, TypeScript, RxJS, SCSS"],
            ["Backend", "FastAPI, SQLAlchemy, Pydantic, httpx"],
            ["Base de données", "PostgreSQL (~45 tables)"],
            ["IA", "Gemini, Ollama (repli), moteur déterministe"],
            ["Intégration", "FedEx Track API, Jarvis-OS"],
            ["Tests backend", "pytest (~50 fichiers)"],
        ],
    )
    p(doc, "Fichiers clés : backend/app/main.py, frontend/src/app/app.routes.ts, backend/app/core/database.py")

    # --- 2 Réalisation ---
    h1(doc, "2. Chapitre Réalisation (texte académique)")
    h2(doc, "2.1 Introduction")
    p(
        doc,
        "Le présent chapitre expose la mise en œuvre concrète de la plateforme Globex FedEx, assistant "
        "conversationnel orienté logistique et suivi de colis. La réalisation s'appuie sur une architecture "
        "three-tier : interface Angular 17, API FastAPI et base PostgreSQL. Trois profils — client, employé "
        "et administrateur — interagissent avec un chatbot intelligent, consultent des expéditions FedEx, "
        "gèrent des tickets et supervisent la plateforme via un centre de commandement.",
    )
    h2(doc, "2.2 Environnement technique")
    p(
        doc,
        "Backend port 8000, frontend port 4200, configuration via .env. L'initialisation du schéma repose "
        "sur create_all() et migrations SQL idempotentes (ALTER TABLE IF NOT EXISTS), sans Alembic.",
    )
    h2(doc, "2.3 Architecture implémentée")
    p(
        doc,
        "Patron client-serveur REST + WebSocket (chat admin-employé). Trois portails dans une SPA isolés "
        "par guards Angular (clientPortalGuard, employeePortalGuard, adminGuard). Sidecar Jarvis via "
        "jarvis/bridge.py et ouverture UI externe JARVIS_UI_URL.",
    )
    h2(doc, "2.4 Backend")
    p(
        doc,
        "main.py monte les routeurs auth, chat, tracking, employee, admin, notifications, reports, "
        "security, settings, globex_agent, agent_missions. Services structurants : chatbot_service.py, "
        "fedex_service.py, admin_copilot_service.py, command_center_service.py, prompt_guard_service.py.",
    )
    h2(doc, "2.5 Frontend")
    p(
        doc,
        "Features modulaires (auth, chat, history, employee, admin). Chat-page comme cœur client. "
        "Employee-shell et admin-page comme conteneurs. i18n FR/EN/AR avec RTL admin.",
    )
    h2(doc, "2.6 Intégration FedEx")
    p(
        doc,
        "fedex_service.py : OAuth cache, Track API, whitelist sandbox (fedex_sandbox_whitelist.py), "
        "cache shipment_cache et historique tracking_request.",
    )
    h2(doc, "2.7 Module IA")
    p(
        doc,
        "Pipeline chat : prompt guard → export intent → tracking → GPT orchestrator. Copilot admin : "
        "cascade Gemini → Ollama → Jarvis → déterministe (gemini_budget.py, llm_router.py).",
    )
    h2(doc, "2.8 Sécurité")
    p(
        doc,
        "JWT, guards, prompt guard, validation admin des préférences, incidents sécurité, activity logs. "
        "Documentation : docs/prompt-security.md.",
    )
    h2(doc, "2.9 Conclusion du chapitre")
    p(
        doc,
        "Plateforme complète (~230 endpoints), modules IA avec repli, limites : tests frontend absents, "
        "composants admin partiellement connectés, fallbacks demo UI.",
    )
    doc.add_page_break()

    # --- 3 Mermaid ---
    h1(doc, "3. Architecture et diagrammes Mermaid")
    p(doc, "Copier chaque bloc dans https://mermaid.live pour export PNG/PDF des figures.")
    h2(doc, "3.1 Architecture globale")
    code(
        doc,
        """flowchart TB
  WEB[Navigateur] --> ANG[Angular 17 :4200]
  ANG --> API[FastAPI :8000]
  API --> PG[(PostgreSQL)]
  API --> FEDEX[FedEx API]
  API --> GEM[Gemini/Ollama]
  ANG --> JAR[Jarvis-OS :8013]""",
    )
    h2(doc, "3.2 Cas d'utilisation (acteurs)")
    p(doc, "Acteurs : Client, Employé, Administrateur. FedEx API et Services IA en dépendances externes.")
    h2(doc, "3.3 Séquence chatbot")
    p(
        doc,
        "POST /chat/message → Prompt Guard → chatbot_service → export? → tracking FedEx → "
        "run_gpt_turn → persistance ChatMessage → réponse JSON.",
    )
    h2(doc, "3.4 Séquence tracking")
    p(
        doc,
        "GET /tracking/{tn} → assert_sandbox_whitelist → get_shipment → OAuth FedEx → "
        "cache → TrackingResponse.",
    )
    h2(doc, "3.5 Séquence export Excel")
    p(
        doc,
        "chat_export_service → export_download metadata → GET /export/tracking-history.xlsx → openpyxl.",
    )
    h2(doc, "3.6 Modèle de données (entités principales)")
    p(
        doc,
        "users, chat_sessions, chat_messages, tracking_requests, shipment_cache, support_tickets, "
        "security_incidents, agent_missions, knowledge_chunks, activity_logs (~45 tables au total).",
    )
    doc.add_page_break()

    # --- 4 Frontend ---
    h1(doc, "4. Inventaire frontend Angular")
    h2(doc, "4.1 Routes principales")
    routes = [
        ["/login, /register", "Auth client"],
        ["/employee/login, /register, /activate", "Auth employé"],
        ["/chat, /chat/shared/:token", "Chat client"],
        ["/history, /documents, /espace", "Espace client"],
        ["/settings/:tab", "Paramètres client"],
        ["/help, /notifications", "Aide et notifications"],
        ["/employee/*", "Portail employé (dashboard, clients, tracking, support, ai-agent…)"],
        ["/admin", "Shell admin + sections internes"],
        ["/admin/agent-missions/*", "Missions agent (liste, new, :id, edit)"],
    ]
    table(doc, ["Route", "Description"], routes)

    h2(doc, "4.2 Services Angular (29 fichiers)")
    services = [
        ["auth.service.ts", "/auth/*"],
        ["chatbot.service.ts", "POST /chat/message"],
        ["chat-session.service.ts", "/chat/sessions/*, /chat/collections, partage"],
        ["tracking.service.ts", "/tracking/{tn}, POD"],
        ["history.service.ts", "/history, export Excel"],
        ["support.service.ts", "/api/support/*"],
        ["help-center.service.ts", "/api/help/*"],
        ["user-notifications.service.ts", "/api/notifications/me"],
        ["employee-portal.service.ts", "/api/employee/*"],
        ["employee-admin-chat-socket.service.ts", "WS /api/employee/admin-chat/ws"],
        ["admin.service.ts", "/admin/*, support admin, employee-chat"],
        ["admin-ai.service.ts", "/admin/ai-assistant/*"],
        ["command-center.service.ts", "/admin/command-center"],
        ["notifications.service.ts", "/api/admin/notifications/*"],
        ["reports.service.ts", "/api/reports/*"],
        ["agent-missions.service.ts", "/admin/agent-missions/*"],
        ["gpt-knowledge.service.ts", "/admin/gpt/knowledge/*"],
        ["system-settings.service.ts", "/api/settings/*, /api/system/*"],
        ["agent-window.service.ts", "/admin/agent-window/*"],
        ["admin-conversations.service.ts", "/admin/conversations"],
    ]
    table(doc, ["Service", "API principales"], services)
    p(doc, "Services UI-only (sans HTTP direct) : sidebar-sessions, conversation-sidebar-bridge, employee-*-state, asset-preload.")

    h2(doc, "4.3 Composants (~82 fichiers .component.ts)")
    p(
        doc,
        "Client : chat-page + sidebar, message-list, conversation-thread, chat-hero, share-conversation… "
        "Employé : employee-shell, dashboard, clients, tracking, support, admin-chat, ai-agent… "
        "Admin : admin-page + dashboard, ai-assistant, tracking, users, security, reports, agent-missions… "
        "Shared : shipment-card, tracking-map, shipment-route-map.",
    )
    doc.add_page_break()

    # --- 5 Admin modules ---
    h1(doc, "5. Modules administrateur")
    admin_rows = [
        ["Dashboard", "Command center, KPIs, copilot intégré", "admin-dashboard/", "Complet"],
        ["Assistant IA", "Copilot, exports, pièces jointes", "admin-ai-assistant/", "Demo conv. si API vide"],
        ["AI Health", "Santé providers IA", "admin-ai-health/", "Lecture seule"],
        ["Base GPT", "Upload, reindex RAG", "admin-gpt-knowledge/", "Complet si pgvector OK"],
        ["Conversations", "Sessions client + messaging hub", "admin-conversations/", "sendMessage() sans API"],
        ["Tracking", "Expéditions live", "admin-tracking/", "KPIs demo en fallback"],
        ["Notifications", "Centre notif admin", "admin-notifications/", "Polling, pas SSE UI"],
        ["Utilisateurs", "CRUD, invite, suspend", "admin-users/", "Permissions statiques"],
        ["Rapports", "Catalogue, génération IA", "admin-reports/", "Complet si backend OK"],
        ["Agent Missions", "Workflow, exécution", "agent-missions/", "Avancé, dépend agents"],
        ["Audit logs", "Journaux activité", "admin-audit-logs/", "KPIs partiellement fictifs"],
        ["Sécurité", "Incidents, scan, agent", "admin-security/", "Relativement complet"],
        ["Paramètres", "Système, intégrations", "admin-settings/", "Complet"],
        ["Préférences pending", "Validation prefs client", "admin-page inline", "UI non accessible menu"],
    ]
    table(doc, ["Module", "Rôle", "Dossier", "Statut"], admin_rows)
    p(doc, "Composants non montés : admin-agent-window, admin-support-tickets (importés mais absents du template).")

    doc.add_page_break()

    # --- 6 Tests ---
    h1(doc, "6. Plan de tests (extrait)")
    p(doc, "Environnement : backend :8000, frontend :4200, PostgreSQL globex_fedex, comptes client/employé/admin.")
    test_rows = [
        ["AUTH-01", "Inscription client", "Formulaire register", "Compte créé", "À exécuter"],
        ["CHAT-01", "Message chat", "POST /chat/message", "Réponse IA persistée", "À exécuter"],
        ["CHAT-05", "Tracking whitelist", "Numéro sandbox valide", "Carte colis FedEx", "À exécuter"],
        ["CHAT-06", "Tracking refusé", "Numéro hors whitelist", "Erreur sandbox", "À exécuter"],
        ["HIST-03", "Export Excel", "Export historique", "Fichier .xlsx", "Auto: test_logs_excel_export"],
        ["EMP-16", "WebSocket admin-chat", "Connexion WS", "Messages push", "À exécuter"],
        ["ADM-C04", "Message admin conv", "Composer Send", "Message persisté", "Partiel: pas d'API"],
        ["ADM-AI-02", "Copilot requête", "Question KPI", "Réponse data-driven", "Auto: test_admin_copilot"],
        ["SEC-03", "Prompt injection", "Input malveillant", "Bloqué", "Auto: test_prompt_guard"],
    ]
    table(doc, ["ID", "Cas", "Étapes", "Attendu", "Obtenu"], test_rows)
    p(doc, "Total ~140 cas. Commande : cd backend && pytest tests/ -v")
    p(doc, "Frontend : 1 seul spec (app.component.spec.ts), pas d'E2E Playwright/Cypress.")

    doc.add_page_break()

    # --- 7 Difficultés ---
    h1(doc, "7. Difficultés techniques et solutions")
    diff_rows = [
        ["Schéma DB sans Alembic", "Migrations SQL idempotentes au démarrage", "database.py"],
        ["FedEx sandbox limité", "Whitelist + messages UX", "fedex_sandbox_whitelist.py"],
        ["Hallucinations tracking", "Réponses déterministes / anti-hallucination", "llm/orchestrator.py"],
        ["Quota Gemini 429", "Budget + cascade Ollama/local", "gemini_budget.py, llm_router.py"],
        ["Prompt injection", "Prompt guard + validation admin prefs", "prompt_guard_service.py"],
        ["pgvector absent", "Recherche cosinus Python", "vector_store.py"],
        ["Images chat sans migration", "Encodage dans message_text", "message_attachment.py"],
        ["3 portails une SPA", "Guards par rôle", "portal.guard.ts"],
        ["Chat admin temps réel", "WebSocket hub", "employee.py, employee-admin-chat-socket.service.ts"],
        ["Sidecar Jarvis", "HTTP bridge + UI externe", "jarvis/bridge.py, api.config.ts"],
    ]
    table(doc, ["Difficulté", "Solution", "Fichiers"], diff_rows)

    doc.add_page_break()

    # --- 8 Captures ---
    h1(doc, "8. Captures d'écran recommandées pour le rapport")
    cap_rows = [
        ["Fig. 1", "/login", "Page connexion client"],
        ["Fig. 2", "/chat", "Interface chat avec sidebar et réponse tracking"],
        ["Fig. 3", "/history", "Historique + drawer détail colis"],
        ["Fig. 4", "/help?support=1", "Centre d'aide et ticket support"],
        ["Fig. 5", "/employee", "Dashboard employé"],
        ["Fig. 6", "/employee/tracking", "Liste expéditions employé"],
        ["Fig. 7", "/employee/admin-chat", "Chat employé-admin"],
        ["Fig. 8", "/admin", "Command center admin"],
        ["Fig. 9", "/admin (section IA)", "Copilot administrateur"],
        ["Fig. 10", "/admin (section Users)", "Gestion utilisateurs"],
        ["Fig. 11", "/admin/agent-missions", "Agent missions workflow"],
        ["Fig. 12", "localhost:8000/docs", "Swagger FastAPI"],
        ["Fig. 13", "Erreur sandbox", "Message whitelist refusé"],
        ["Fig. 14", "localhost:8013", "UI Jarvis-OS (optionnel)"],
    ]
    table(doc, ["Figure", "URL / contexte", "Légende suggérée"], cap_rows)

    doc.add_page_break()

    # --- 9 Guide ---
    h1(doc, "9. Guide de démarrage et soutenance")
    p(doc, "1. Démarrer PostgreSQL (globex_fedex). 2. backend : copier .env.example → .env, pip install -r requirements.txt, uvicorn app.main:app --reload --port 8000. 3. frontend : npm install, ng serve --port 4200. 4. Optionnel Jarvis :8013.")
    p(doc, "Numéros FedEx sandbox whitelist : 881354459588, 397773675776, etc. (voir fedex_sandbox_whitelist.py).")
    p(doc, "Scénario soutenance (10 min) : login client → question tracking → historique → export → login admin → dashboard → copilot → sécurité.")

    # --- 10 Synthèse ---
    h1(doc, "10. Synthèse réalisé / partiel / non réalisé")
    syn_rows = [
        ["Auth multi-rôles", "Réalisé"],
        ["Chat client + FedEx", "Réalisé"],
        ["Export Excel", "Réalisé"],
        ["Portail employé complet", "Réalisé"],
        ["Copilot admin", "Réalisé (avec repli)"],
        ["Agent missions", "Partiel"],
        ["Composer conv. admin", "Non réalisé (UI seule)"],
        ["File prefs admin menu", "Non exposé UI"],
        ["Agent window in-app", "Non monté"],
        ["Tests frontend E2E", "Non réalisé"],
        ["Tests backend pytest", "Réalisé (~50 fichiers)"],
    ]
    table(doc, ["Fonctionnalité", "Statut"], syn_rows)

    doc.add_page_break()

    # --- 11 Annexes ---
    h1(doc, "11. Annexes")
    h2(doc, "11.1 Backend — routeurs montés")
    p(
        doc,
        "auth, chat, tracking, history, export_excel, employee, admin, security_admin, settings_admin, "
        "notifications, reports, help, support, user_notifications, system, fedex_locations, "
        "fedex_webhooks, globex_agent, agent_missions, agent_window, gpt_knowledge (~230 URLs uniques).",
    )
    h2(doc, "11.2 Base de données")
    p(doc, "~45 tables PostgreSQL. Entités : users, chat_*, tracking_*, support_*, notifications, "
         "security_incidents, agent_missions, gpt/knowledge, activity_logs, reports, employee_admin_chat.")
    h2(doc, "11.3 Tests automatisés backend (échantillon)")
    p(
        doc,
        "test_admin_copilot_pipeline.py, test_prompt_guard.py, test_user_suspension_logic.py, "
        "test_copilot_final_fixes.py, test_all_62_tools.py, test_globex_agent_http.py, "
        "test_vector_store.py, test_logs_excel_export.py",
    )
    h2(doc, "11.4 Références projet")
    p(doc, "GUIDE_FICHIERS.md, GUIDE_MODIFICATION_RAPIDE.md, docs/prompt-security.md")

    doc.save(DOCX_PATH)
    return DOCX_PATH


def build_pdf() -> Path:
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=12,
        textColor=colors.HexColor("#4A0080"),
    )
    h2_style = ParagraphStyle("CustomH2", parent=styles["Heading2"], fontSize=13, spaceAfter=8)
    body = styles["BodyText"]

    story: list = []
    story.append(Paragraph("RAPPORT PFE — Globex FedEx Chatbot", title_style))
    story.append(Paragraph(f"Document consolidé — {date.today().strftime('%d/%m/%Y')}", body))
    story.append(Spacer(1, 0.5 * cm))
    story.append(
        Paragraph(
            "Ce PDF reprend la synthèse de la discussion technique. "
            "Le fichier Word (.docx) associé contient le détail complet (tableaux, annexes).",
            body,
        )
    )
    story.append(Spacer(1, 0.5 * cm))

    sections = [
        ("1. Stack", "Angular 17 + FastAPI + PostgreSQL + Gemini/Ollama + FedEx API + Jarvis sidecar."),
        ("2. Réalisation", "Three-tier, 3 portails (client/employé/admin), ~230 endpoints, copilot cascade."),
        ("3. Admin", "13 modules ; lacunes : composer conversations, prefs menu, agent-window non monté."),
        ("4. Tests", "~140 cas manuels + ~50 fichiers pytest backend ; frontend E2E absent."),
        ("5. Difficultés", "Whitelist FedEx, anti-hallucination, prompt guard, fallbacks LLM, migrations idempotentes."),
        ("6. Captures", "14 figures recommandées (chat, admin, swagger, sandbox error)."),
    ]
    for title, content in sections:
        story.append(Paragraph(title, h2_style))
        story.append(Paragraph(content, body))
        story.append(Spacer(1, 0.3 * cm))

    story.append(Paragraph("Synthèse statuts", h2_style))
    data = [
        ["Fonctionnalité", "Statut"],
        ["Auth + Chat + FedEx", "Réalisé"],
        ["Portail employé", "Réalisé"],
        ["Copilot admin", "Réalisé (repli)"],
        ["Composer conv. admin", "Non réalisé"],
        ["Tests E2E frontend", "Non réalisé"],
    ]
    t = Table(data, colWidths=[8 * cm, 6 * cm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#6D28FF")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 0.5 * cm))
    story.append(
        Paragraph(
            f"Fichier Word détaillé : {DOCX_PATH.name}",
            body,
        )
    )

    doc = SimpleDocTemplate(str(PDF_PATH), pagesize=A4, rightMargin=2 * cm, leftMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm)
    doc.build(story)
    return PDF_PATH


if __name__ == "__main__":
    docx = build_docx()
    pdf = build_pdf()
    print(f"DOCX: {docx}")
    print(f"PDF:  {pdf}")
