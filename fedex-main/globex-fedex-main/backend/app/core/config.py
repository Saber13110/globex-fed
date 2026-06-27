from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Globex FedEx Chatbot API"
    app_version: str = "2.4.0"
    debug: bool = False

    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/globex_fedex"

    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    # Compte administrateur unique (créé au démarrage, jamais via l'inscription).
    admin_email: str = "admin@globex.ma"
    admin_password: str = "Admin@Globex2024"
    admin_full_name: str = "Administrateur Globex"

    # Envoi d'emails (SMTP) — utilisé pour les invitations et notifications.
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True

    # Google OAuth (connexion via Google).
    google_client_id: str = ""

    # Double authentification (code OTP par email après mot de passe).
    two_factor_enabled: bool = True

    # Limitation des tentatives de connexion (par IP et par email).
    login_rate_limit_attempts: int = 10
    login_rate_limit_window_seconds: int = 900

    # URL du frontend, pour construire les liens (invitations, etc.).
    frontend_base_url: str = "http://localhost:4200"

    # LLM — Jarvis (Ollama llama3.2:3b) cerveau admin, Gemini réservé embeddings / client
    llm_enabled: bool = True
    llm_primary_provider: str = "ollama"  # ollama (Jarvis) | gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_pro_model: str = "gemini-2.5-pro"
    gemini_fallback_models: str = "gemini-2.5-flash-lite,gemini-2.0-flash-lite,gemini-2.0-flash-001"
    gemini_retry_on_503: bool = True
    gemini_timeout_seconds: float = 45.0
    gemini_max_calls_per_request: int = 2
    gemini_max_calls_agent_mode: int = 4
    gemini_quota_cooldown_seconds: int = 900
    llm_fallback_provider: str = "ollama"
    ai_timeout_seconds: float = 30.0
    ai_tool_timeout_seconds: float = 5.0
    ai_llm_gemini_timeout_seconds: float = 15.0
    ai_llm_ollama_timeout_seconds: float = 120.0
    ai_enable_local_fallback: bool = True
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b-instruct"
    ollama_timeout_seconds: float = 120.0
    llm_max_prompt_chars: int = 1500

    prompt_guard_enabled: bool = True
    prompt_guard_block_threshold: int = 70
    prompt_guard_warn_threshold: int = 40
    prompt_guard_block_chat: bool = True

    # Désactivé par défaut : sans SMTP + email admin réel, utiliser l’onglet admin.
    notify_admin_on_preference_submit: bool = False
    admin_notify_email: str = ""
    # Si true : statut colis formaté sans LLM quand FedEx renvoie des données réelles
    use_deterministic_fedex_reply: bool = False
    # Réponses client mockées (tests hors Gemini/Ollama)
    mock_client_chat_enabled: bool = False
    # Rétrocompatibilité (.env historique)
    llm_base_url: str = "http://localhost:11434"
    llm_model: str = "gemma3:12b"
    llm_timeout_seconds: float = 120.0

    gpt_tools_enabled: bool = True
    gpt_tool_max_rounds: int = 4
    # Phase 3 client — boucle outils Ollama (PDF, export, chat agentique)
    client_tool_loop_enabled: bool = True
    # Phase 2 — bonjour/FAQ via Ollama léger (sans boucle outils) ; false = rollback tool loop
    client_conversational_fast_path: bool = True
    # Capacités client progressives : chat | fedex | pdf | excel (virgules)
    client_agent_capabilities: str = "chat"

    # Phase 3 — RAG vectoriel (PGVector + embeddings Gemini)
    gpt_rag_vector_enabled: bool = True
    gpt_rag_pgvector_enabled: bool = True
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_embedding_fallback_models: str = "text-embedding-004"
    gemini_embedding_dimensions: int = 768
    gpt_chunk_size: int = 900
    gpt_chunk_overlap: int = 150
    gpt_rag_vector_top_k: int = 6
    gpt_rag_hybrid_min_score: float = 0.42
    knowledge_upload_max_mb: int = 15
    knowledge_upload_dir: str = "uploads/knowledge"

    fedex_enabled: bool = False
    fedex_base_url: str = "https://apis-sandbox.fedex.com"
    fedex_client_id: str = ""
    fedex_client_secret: str = ""
    fedex_account_number: str = ""
    fedex_locale: str = "fr_CA"
    fedex_timeout_seconds: float = 20.0
    # Location Search API — si vides, réutilise FEDEX_CLIENT_ID / FEDEX_CLIENT_SECRET
    fedex_location_client_id: str = ""
    fedex_location_client_secret: str = ""
    fedex_visibility_simulation_enabled: bool = True
    fedex_visibility_sync_on_track: bool = True
    fedex_webhook_secret: str = ""

    # Agent client — surveillance colis en arrière-plan (secondes, défaut 2 min)
    shipment_watch_enabled: bool = True
    shipment_watch_interval_seconds: int = 60

    # IDS sécurité — détection prompts malveillants, règles logs, analyse IA
    security_ids_enabled: bool = True
    security_ids_scan_interval_seconds: int = 120
    security_ids_ai_enabled: bool = True
    security_ids_ai_interval_seconds: int = 900
    security_auto_mode_default: bool = False
    # Au-delà de N tentatives d'attaque (fenêtre glissante), alerte admin pour suspension manuelle
    security_admin_notify_after_attempts: int = 2
    security_admin_notify_window_hours: int = 24

    # Jarvis-OS — Agent Window admin (sidecar LLM)
    jarvis_enabled: bool = True
    jarvis_base_url: str = "http://127.0.0.1:8010"
    jarvis_api_token: str = ""
    jarvis_timeout_seconds: float = 120.0
    jarvis_inject_context: bool = True
    jarvis_context_max_chars: int = 2000
    jarvis_max_history_turns: int = 10

    # Globex OS Agent — noyau indépendant du copilot admin
    globex_agent_enabled: bool = True
    globex_proactive_enabled: bool = True
    globex_proactive_interval_seconds: int = 300
    globex_proactive_sla_limit: int = 10
    globex_proactive_dormant_days: int = 30
    globex_proactive_dormant_limit: int = 10


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    # Rétrocompat : LLM_BASE_URL / LLM_MODEL si OLLAMA_* non définis
    if settings.ollama_base_url == "http://localhost:11434" and settings.llm_base_url != settings.ollama_base_url:
        object.__setattr__(settings, "ollama_base_url", settings.llm_base_url)
    if settings.ollama_model == "gemma3:12b" and settings.llm_model not in ("gemma3:12b", ""):
        object.__setattr__(settings, "ollama_model", settings.llm_model)
    if settings.ollama_timeout_seconds == 120.0 and settings.llm_timeout_seconds != 120.0:
        object.__setattr__(settings, "ollama_timeout_seconds", settings.llm_timeout_seconds)
    return settings
