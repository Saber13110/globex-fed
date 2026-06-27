from collections.abc import Generator
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models.base import Base

settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def seed_admin() -> None:
    """Crée (ou répare) l'unique compte administrateur. Jamais créé via l'inscription."""
    from app.core.security import get_password_hash
    from app.models.user import User, UserRole

    settings = get_settings()
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == settings.admin_email.lower()).one_or_none()
        if admin is None:
            admin = User(
                full_name=settings.admin_full_name,
                email=settings.admin_email.lower(),
                password_hash=get_password_hash(settings.admin_password),
                role=UserRole.admin.value,
                preferred_language="fr",
                organization_id=str(uuid.uuid4()),
            )
            db.add(admin)
        elif admin.role != UserRole.admin.value:
            admin.role = UserRole.admin.value
        db.commit()
    finally:
        db.close()


def init_db() -> None:
    """Crée les tables si elles n'existent pas (MVP / dev)."""
    import app.models  # noqa: F401 — enregistre tous les modèles SQLAlchemy

    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS chat_collections ("
                "id SERIAL PRIMARY KEY, "
                "user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                "name VARCHAR(120) NOT NULL, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        conn.execute(text("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS is_pinned BOOLEAN NOT NULL DEFAULT false"))
        conn.execute(
            text("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()")
        )
        conn.execute(text("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT false"))
        conn.execute(text("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS tags TEXT NOT NULL DEFAULT ''"))
        conn.execute(
            text(
                "ALTER TABLE chat_sessions "
                "ADD COLUMN IF NOT EXISTS collection_id INTEGER REFERENCES chat_collections(id) ON DELETE SET NULL"
            )
        )
        conn.execute(text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS source VARCHAR(32) NOT NULL DEFAULT 'unknown'"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS organization_id VARCHAR(64)"))
        # Statut du compte (workflow de validation des employés par l'admin).
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'active'"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS activation_token VARCHAR(96)"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS activation_expires_at TIMESTAMPTZ"))
        conn.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_activation_token ON users (activation_token)")
        )
        # Les comptes existants sont considérés actifs.
        conn.execute(text("UPDATE users SET status = 'active' WHERE status IS NULL OR status = ''"))
        # Les anciens comptes « invited » (2e clic d'activation) passent en actifs.
        conn.execute(
            text(
                "UPDATE users SET status = 'active', activation_token = NULL, activation_expires_at = NULL "
                "WHERE status = 'invited'"
            )
        )
        # Migration des rôles : l'ancien rôle "user" devient "client".
        conn.execute(text("UPDATE users SET role = 'client' WHERE role = 'user'"))
        # L'ancien système d'invitations (flux pré-validation) n'est plus utilisé.
        conn.execute(text("DROP TABLE IF EXISTS invitations"))
        rows = conn.execute(text("SELECT id FROM users WHERE organization_id IS NULL OR organization_id = ''")).fetchall()
        for row in rows:
            conn.execute(
                text("UPDATE users SET organization_id = :organization_id WHERE id = :id"),
                {"organization_id": str(uuid.uuid4()), "id": row[0]},
            )
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_organization_id ON users (organization_id)"))
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS user_sessions ("
                "id SERIAL PRIMARY KEY, "
                "user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                "token_id VARCHAR(64) NOT NULL UNIQUE, "
                "browser VARCHAR(80) NOT NULL DEFAULT 'Unknown', "
                "machine VARCHAR(80) NOT NULL DEFAULT 'Unknown', "
                "location VARCHAR(120) NOT NULL DEFAULT 'Unknown', "
                "is_active BOOLEAN NOT NULL DEFAULT true, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_sessions_user_id ON user_sessions (user_id)"))
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS shared_conversation_links ("
                "id SERIAL PRIMARY KEY, "
                "session_id INTEGER NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE, "
                "owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                "share_token VARCHAR(96) NOT NULL UNIQUE, "
                "include_tracking_details BOOLEAN NOT NULL DEFAULT false, "
                "is_active BOOLEAN NOT NULL DEFAULT true, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_shared_conversation_links_session_id ON shared_conversation_links (session_id)")
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_shared_conversation_links_owner_user_id ON shared_conversation_links (owner_user_id)")
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS login_otp_challenges ("
                "id SERIAL PRIMARY KEY, "
                "user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                "challenge_token VARCHAR(96) NOT NULL UNIQUE, "
                "otp_hash VARCHAR(255) NOT NULL, "
                "attempts INTEGER NOT NULL DEFAULT 0, "
                "expires_at TIMESTAMPTZ NOT NULL, "
                "last_sent_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_login_otp_challenges_user_id ON login_otp_challenges (user_id)"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS qr_login_token_digest VARCHAR(64)"))
        conn.execute(
            text(
                "ALTER TABLE tracking_requests "
                "ADD COLUMN IF NOT EXISTS session_id INTEGER REFERENCES chat_sessions(id) ON DELETE SET NULL"
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_tracking_requests_session_id ON tracking_requests (session_id)")
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_qr_login_token_digest "
                "ON users (qr_login_token_digest) WHERE qr_login_token_digest IS NOT NULL"
            )
        )
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS response_preferences TEXT NOT NULL DEFAULT ''"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS quota_messages_per_day INTEGER"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS quota_trackings_per_day INTEGER"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS quota_exports_per_day INTEGER"))
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS preference_submissions ("
                "id SERIAL PRIMARY KEY, "
                "user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                "proposed_text TEXT NOT NULL, "
                "status VARCHAR(20) NOT NULL DEFAULT 'pending', "
                "risk_score INTEGER NOT NULL DEFAULT 0, "
                "risk_reasons TEXT NOT NULL DEFAULT '[]', "
                "rejection_note VARCHAR(500) NOT NULL DEFAULT '', "
                "reviewed_by INTEGER REFERENCES users(id) ON DELETE SET NULL, "
                "reviewed_at TIMESTAMPTZ, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_preference_submissions_user_status "
                "ON preference_submissions (user_id, status)"
            )
        )
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS preference_profile_json TEXT NOT NULL DEFAULT '{}'"))
        conn.execute(
            text("ALTER TABLE preference_submissions ADD COLUMN IF NOT EXISTS structured_json TEXT NOT NULL DEFAULT '{}'")
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS activity_logs ("
                "id SERIAL PRIMARY KEY, "
                "user_id INTEGER REFERENCES users(id) ON DELETE SET NULL, "
                "actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL, "
                "level VARCHAR(16) NOT NULL DEFAULT 'INFO', "
                "category VARCHAR(32) NOT NULL DEFAULT 'system', "
                "action VARCHAR(64) NOT NULL, "
                "message TEXT NOT NULL, "
                "metadata_json TEXT NOT NULL DEFAULT '', "
                "ip_address VARCHAR(64) NOT NULL DEFAULT '', "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_activity_logs_user_id ON activity_logs (user_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_activity_logs_created_at ON activity_logs (created_at DESC)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_activity_logs_category ON activity_logs (category)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_activity_logs_level ON activity_logs (level)"))
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS support_tickets ("
                "id SERIAL PRIMARY KEY, "
                "user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                "subject VARCHAR(200) NOT NULL, "
                "message TEXT NOT NULL, "
                "status VARCHAR(20) NOT NULL DEFAULT 'open', "
                "admin_note VARCHAR(500) NOT NULL DEFAULT '', "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_support_tickets_status ON support_tickets (status, created_at DESC)")
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS support_ticket_messages ("
                "id SERIAL PRIMARY KEY, "
                "ticket_id INTEGER NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE, "
                "author_role VARCHAR(16) NOT NULL, "
                "author_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL, "
                "body TEXT NOT NULL, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_support_ticket_messages_ticket_id ON support_ticket_messages (ticket_id)")
        )
        conn.execute(text("ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS ticket_number VARCHAR(32)"))
        conn.execute(text("ALTER TABLE support_tickets ALTER COLUMN ticket_number DROP NOT NULL"))
        conn.execute(text("ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS category VARCHAR(32) NOT NULL DEFAULT 'other'"))
        conn.execute(text("ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS priority VARCHAR(16) NOT NULL DEFAULT 'medium'"))
        conn.execute(text("ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS attachment_url VARCHAR(512)"))
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_support_tickets_ticket_number "
                "ON support_tickets (ticket_number) WHERE ticket_number IS NOT NULL"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS client_notifications ("
                "id SERIAL PRIMARY KEY, "
                "user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                "kind VARCHAR(32) NOT NULL DEFAULT 'support_reply', "
                "title VARCHAR(200) NOT NULL, "
                "message TEXT NOT NULL DEFAULT '', "
                "link VARCHAR(255) NOT NULL DEFAULT '/support', "
                "reference_id INTEGER, "
                "is_read BOOLEAN NOT NULL DEFAULT false, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_client_notifications_user_id ON client_notifications (user_id)")
        )
        conn.execute(text("ALTER TABLE client_notifications ADD COLUMN IF NOT EXISTS sender_id INTEGER REFERENCES users(id) ON DELETE SET NULL"))
        conn.execute(text("ALTER TABLE client_notifications ADD COLUMN IF NOT EXISTS sender_role VARCHAR(16)"))
        conn.execute(text("ALTER TABLE client_notifications ADD COLUMN IF NOT EXISTS priority VARCHAR(16) NOT NULL DEFAULT 'medium'"))
        conn.execute(text("ALTER TABLE client_notifications ADD COLUMN IF NOT EXISTS related_tracking_number VARCHAR(64) NOT NULL DEFAULT ''"))
        conn.execute(text("ALTER TABLE client_notifications ADD COLUMN IF NOT EXISTS read_at TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE client_notifications ADD COLUMN IF NOT EXISTS related_document_id INTEGER"))
        conn.execute(text("ALTER TABLE client_notifications ADD COLUMN IF NOT EXISTS related_client_id INTEGER"))
        conn.execute(text("ALTER TABLE client_notifications ADD COLUMN IF NOT EXISTS role_target VARCHAR(16) NOT NULL DEFAULT 'client'"))
        conn.execute(text("UPDATE client_notifications SET kind = 'admin_reply' WHERE kind = 'support_reply'"))
        conn.execute(text("ALTER TABLE support_ticket_messages ADD COLUMN IF NOT EXISTS attachment_url VARCHAR(512)"))
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS system_settings ("
                "id INTEGER PRIMARY KEY DEFAULT 1, "
                "settings_json TEXT NOT NULL DEFAULT '{}', "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS report_runs ("
                "id SERIAL PRIMARY KEY, "
                "slug VARCHAR(64) NOT NULL, "
                "name VARCHAR(160) NOT NULL, "
                "category VARCHAR(32) NOT NULL, "
                "format VARCHAR(16) NOT NULL, "
                "period_label VARCHAR(64) NOT NULL DEFAULT '', "
                "status VARCHAR(20) NOT NULL DEFAULT 'completed', "
                "file_path VARCHAR(512) NOT NULL DEFAULT '', "
                "file_size INTEGER NOT NULL DEFAULT 0, "
                "row_count INTEGER NOT NULL DEFAULT 0, "
                "generated_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL, "
                "error_message TEXT NOT NULL DEFAULT '', "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                "completed_at TIMESTAMPTZ"
                ")"
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_report_runs_slug ON report_runs (slug)"))
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS report_schedules ("
                "id SERIAL PRIMARY KEY, "
                "name VARCHAR(160) NOT NULL, "
                "slug VARCHAR(64) NOT NULL, "
                "frequency VARCHAR(20) NOT NULL, "
                "run_time VARCHAR(8) NOT NULL DEFAULT '08:00', "
                "recipients VARCHAR(500) NOT NULL DEFAULT '', "
                "format VARCHAR(16) NOT NULL DEFAULT 'xlsx', "
                "active BOOLEAN NOT NULL DEFAULT true, "
                "created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS platform_notifications ("
                "id SERIAL PRIMARY KEY, "
                "external_key VARCHAR(128) NOT NULL UNIQUE, "
                "category VARCHAR(32) NOT NULL, "
                "title VARCHAR(200) NOT NULL, "
                "message TEXT NOT NULL, "
                "tracking_number VARCHAR(64) NOT NULL DEFAULT '', "
                "route VARCHAR(200) NOT NULL DEFAULT '', "
                "priority VARCHAR(16) NOT NULL DEFAULT 'normal', "
                "channel VARCHAR(16) NOT NULL DEFAULT 'web', "
                "icon VARCHAR(32) NOT NULL DEFAULT 'bell', "
                "action_label VARCHAR(64) NOT NULL DEFAULT 'Voir', "
                "action_type VARCHAR(32) NOT NULL DEFAULT '', "
                "action_ref VARCHAR(64) NOT NULL DEFAULT '', "
                "is_read BOOLEAN NOT NULL DEFAULT false, "
                "is_archived BOOLEAN NOT NULL DEFAULT false, "
                "admin_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_platform_notifications_category ON platform_notifications (category)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_platform_notifications_is_read ON platform_notifications (is_read)"))
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS notification_preferences ("
                "id SERIAL PRIMARY KEY, "
                "user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE, "
                "web_enabled BOOLEAN NOT NULL DEFAULT true, "
                "email_enabled BOOLEAN NOT NULL DEFAULT true, "
                "sms_enabled BOOLEAN NOT NULL DEFAULT false, "
                "ai_reports BOOLEAN NOT NULL DEFAULT true, "
                "incidents BOOLEAN NOT NULL DEFAULT true, "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS employee_admin_messages ("
                "id SERIAL PRIMARY KEY, "
                "employee_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                "sender_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                "sender_role VARCHAR(16) NOT NULL, "
                "body TEXT NOT NULL, "
                "attachment_url VARCHAR(512), "
                "is_read BOOLEAN NOT NULL DEFAULT false, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_employee_admin_messages_employee_id ON employee_admin_messages (employee_id)")
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS ai_agent_conversations ("
                "id VARCHAR(36) PRIMARY KEY, "
                "employee_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                "title VARCHAR(200) NOT NULL DEFAULT 'New conversation', "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_ai_agent_conversations_employee_id ON ai_agent_conversations (employee_id)")
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS ai_agent_messages ("
                "id SERIAL PRIMARY KEY, "
                "conversation_id VARCHAR(36) NOT NULL REFERENCES ai_agent_conversations(id) ON DELETE CASCADE, "
                "role VARCHAR(16) NOT NULL, "
                "content TEXT NOT NULL, "
                "intent VARCHAR(64) NOT NULL DEFAULT '', "
                "cards_json TEXT NOT NULL DEFAULT '[]', "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_ai_agent_messages_conversation_id ON ai_agent_messages (conversation_id)")
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS ai_agent_action_logs ("
                "id SERIAL PRIMARY KEY, "
                "employee_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                "action_type VARCHAR(64) NOT NULL, "
                "target_type VARCHAR(64) NOT NULL DEFAULT '', "
                "target_id VARCHAR(64) NOT NULL DEFAULT '', "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_ai_agent_action_logs_employee_id ON ai_agent_action_logs (employee_id)")
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS fedex_visibility_events ("
                "id SERIAL PRIMARY KEY, "
                "tracking_number VARCHAR(64) NOT NULL, "
                "event_type VARCHAR(48) NOT NULL, "
                "event_code VARCHAR(16), "
                "description VARCHAR(512) NOT NULL, "
                "location VARCHAR(255), "
                "occurred_at TIMESTAMPTZ, "
                "source VARCHAR(32) NOT NULL DEFAULT 'fedex_webhook', "
                "fingerprint VARCHAR(128) NOT NULL UNIQUE, "
                "raw_payload_json TEXT NOT NULL DEFAULT '{}', "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_fedex_visibility_events_tracking_number ON fedex_visibility_events (tracking_number)")
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS shipment_pod ("
                "id SERIAL PRIMARY KEY, "
                "tracking_number VARCHAR(64) NOT NULL UNIQUE, "
                "status VARCHAR(128), "
                "delivered_at VARCHAR(64), "
                "delivery_address VARCHAR(512), "
                "received_by_name VARCHAR(255), "
                "signature_available VARCHAR(8) NOT NULL DEFAULT 'false', "
                "carrier_service VARCHAR(128), "
                "raw_fedex_json TEXT NOT NULL DEFAULT '{}', "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_shipment_pod_tracking_number ON shipment_pod (tracking_number)")
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS shipment_watches ("
                "id SERIAL PRIMARY KEY, "
                "user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                "tracking_number VARCHAR(64) NOT NULL, "
                "alert_type VARCHAR(32) NOT NULL DEFAULT 'all', "
                "notify_email BOOLEAN NOT NULL DEFAULT true, "
                "notify_in_app BOOLEAN NOT NULL DEFAULT true, "
                "is_active BOOLEAN NOT NULL DEFAULT true, "
                "last_status VARCHAR(128), "
                "last_notified_status VARCHAR(128), "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_shipment_watches_user_id ON shipment_watches (user_id)")
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_shipment_watches_tracking_number ON shipment_watches (tracking_number)")
        )
        conn.execute(
            text(
                "ALTER TABLE shipment_watches "
                "ADD COLUMN IF NOT EXISTS last_visibility_event_id INTEGER"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE shipment_watches "
                "ADD COLUMN IF NOT EXISTS sandbox_sim_cursor INTEGER NOT NULL DEFAULT 0"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS client_agent_pending ("
                "id VARCHAR(36) PRIMARY KEY, "
                "session_id INTEGER NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE, "
                "user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                "task_type VARCHAR(48) NOT NULL, "
                "initial_message TEXT NOT NULL DEFAULT '', "
                "collected_answers_json TEXT NOT NULL DEFAULT '{}', "
                "status VARCHAR(24) NOT NULL DEFAULT 'questioning', "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_client_agent_pending_session_id ON client_agent_pending (session_id)")
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS security_incidents ("
                "id SERIAL PRIMARY KEY, "
                "user_id INTEGER REFERENCES users(id) ON DELETE SET NULL, "
                "ip_address VARCHAR(64) NOT NULL DEFAULT '', "
                "source VARCHAR(32) NOT NULL, "
                "threat_type VARCHAR(64) NOT NULL, "
                "severity VARCHAR(16) NOT NULL, "
                "score INTEGER NOT NULL DEFAULT 0, "
                "status VARCHAR(24) NOT NULL DEFAULT 'open', "
                "title VARCHAR(200) NOT NULL, "
                "summary TEXT NOT NULL, "
                "evidence_json TEXT NOT NULL DEFAULT '{}', "
                "recommended_action VARCHAR(64) NOT NULL DEFAULT 'monitor', "
                "auto_eligible BOOLEAN NOT NULL DEFAULT false, "
                "dedupe_key VARCHAR(128) NOT NULL UNIQUE, "
                "resolved_at TIMESTAMPTZ, "
                "resolved_by_admin_id INTEGER REFERENCES users(id) ON DELETE SET NULL, "
                "resolution_note TEXT NOT NULL DEFAULT '', "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS security_policies ("
                "id INTEGER PRIMARY KEY DEFAULT 1, "
                "auto_mode_enabled BOOLEAN NOT NULL DEFAULT false, "
                "rules_json TEXT NOT NULL, "
                "ai_ids_enabled BOOLEAN NOT NULL DEFAULT true, "
                "enabled_by_admin_id INTEGER REFERENCES users(id) ON DELETE SET NULL, "
                "enabled_at TIMESTAMPTZ, "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS agent_missions ("
                "id SERIAL PRIMARY KEY, "
                "admin_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                "agent_type VARCHAR(32) NOT NULL, "
                "task_description TEXT NOT NULL, "
                "status VARCHAR(32) NOT NULL DEFAULT 'draft', "
                "schedule_type VARCHAR(16) NOT NULL DEFAULT 'now', "
                "scheduled_at TIMESTAMPTZ, "
                "schedule_time VARCHAR(8) NOT NULL DEFAULT '08:00', "
                "max_items INTEGER NOT NULL DEFAULT 10, "
                "max_duration_minutes INTEGER NOT NULL DEFAULT 15, "
                "require_approval_sensitive BOOLEAN NOT NULL DEFAULT true, "
                "plan_json TEXT NOT NULL DEFAULT '[]', "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                "started_at TIMESTAMPTZ, "
                "finished_at TIMESTAMPTZ, "
                "cancelled_at TIMESTAMPTZ"
                ")"
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_missions_admin_id ON agent_missions (admin_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_missions_status ON agent_missions (status)"))
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS agent_mission_steps ("
                "id SERIAL PRIMARY KEY, "
                "mission_id INTEGER NOT NULL REFERENCES agent_missions(id) ON DELETE CASCADE, "
                "step_order INTEGER NOT NULL, "
                "title VARCHAR(200) NOT NULL, "
                "description TEXT NOT NULL DEFAULT '', "
                "action_type VARCHAR(48) NOT NULL, "
                "is_sensitive BOOLEAN NOT NULL DEFAULT false, "
                "status VARCHAR(24) NOT NULL DEFAULT 'pending', "
                "output_json TEXT NOT NULL DEFAULT '{}', "
                "started_at TIMESTAMPTZ, "
                "finished_at TIMESTAMPTZ"
                ")"
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_mission_steps_mission_id ON agent_mission_steps (mission_id)"))
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS agent_approval_requests ("
                "id SERIAL PRIMARY KEY, "
                "mission_id INTEGER NOT NULL REFERENCES agent_missions(id) ON DELETE CASCADE, "
                "step_id INTEGER NOT NULL REFERENCES agent_mission_steps(id) ON DELETE CASCADE, "
                "action_type VARCHAR(48) NOT NULL, "
                "description TEXT NOT NULL, "
                "payload_json TEXT NOT NULL DEFAULT '{}', "
                "status VARCHAR(16) NOT NULL DEFAULT 'pending', "
                "resolved_by_admin_id INTEGER REFERENCES users(id) ON DELETE SET NULL, "
                "resolved_at TIMESTAMPTZ, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_agent_approval_requests_mission_id ON agent_approval_requests (mission_id)")
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS agent_execution_logs ("
                "id SERIAL PRIMARY KEY, "
                "mission_id INTEGER NOT NULL REFERENCES agent_missions(id) ON DELETE CASCADE, "
                "step_id INTEGER REFERENCES agent_mission_steps(id) ON DELETE SET NULL, "
                "level VARCHAR(16) NOT NULL DEFAULT 'info', "
                "message TEXT NOT NULL, "
                "details_json TEXT NOT NULL DEFAULT '{}', "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_agent_execution_logs_mission_id ON agent_execution_logs (mission_id)")
        )
        conn.execute(
            text("ALTER TABLE agent_missions ADD COLUMN IF NOT EXISTS notify_on_start BOOLEAN NOT NULL DEFAULT true")
        )
        conn.execute(
            text("ALTER TABLE agent_missions ADD COLUMN IF NOT EXISTS notify_on_complete BOOLEAN NOT NULL DEFAULT true")
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS agent_mission_messages ("
                "id SERIAL PRIMARY KEY, "
                "mission_id INTEGER NOT NULL REFERENCES agent_missions(id) ON DELETE CASCADE, "
                "sender VARCHAR(16) NOT NULL, "
                "content TEXT NOT NULL, "
                "metadata_json TEXT NOT NULL DEFAULT '{}', "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_agent_mission_messages_mission_id ON agent_mission_messages (mission_id)")
        )
        # Phase 3 — KB vectorielle
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS knowledge_documents ("
                "id SERIAL PRIMARY KEY, "
                "collection_id INTEGER NOT NULL REFERENCES knowledge_collections(id) ON DELETE CASCADE, "
                "original_filename VARCHAR(255) NOT NULL, "
                "stored_path VARCHAR(512) NOT NULL, "
                "mime_type VARCHAR(128) NOT NULL DEFAULT 'application/octet-stream', "
                "file_size_bytes INTEGER NOT NULL DEFAULT 0, "
                "status VARCHAR(24) NOT NULL DEFAULT 'pending', "
                "error_message TEXT NOT NULL DEFAULT '', "
                "chunk_count INTEGER NOT NULL DEFAULT 0, "
                "uploaded_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_knowledge_documents_collection_id ON knowledge_documents (collection_id)"))
        conn.execute(text("ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS document_id INTEGER REFERENCES knowledge_documents(id) ON DELETE CASCADE"))
        conn.execute(text("ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS chunk_index INTEGER NOT NULL DEFAULT 0"))
        conn.execute(text("ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS embedding_json TEXT"))
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS admin_jarvis_sessions ("
                "id VARCHAR(36) PRIMARY KEY, "
                "admin_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                "jarvis_session_id VARCHAR(64), "
                "title VARCHAR(200) NOT NULL DEFAULT 'Nouvelle conversation', "
                "is_archived BOOLEAN NOT NULL DEFAULT false, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_admin_jarvis_sessions_admin_user_id ON admin_jarvis_sessions (admin_user_id)")
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS admin_jarvis_messages ("
                "id SERIAL PRIMARY KEY, "
                "session_id VARCHAR(36) NOT NULL REFERENCES admin_jarvis_sessions(id) ON DELETE CASCADE, "
                "sender VARCHAR(16) NOT NULL, "
                "message_text TEXT NOT NULL, "
                "jarvis_route VARCHAR(16) NOT NULL DEFAULT '', "
                "latency_ms DOUBLE PRECISION, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_admin_jarvis_messages_session_id ON admin_jarvis_messages (session_id)")
        )

    # PGVector optionnel — transaction séparée (sinon un échec annule toute la migration).
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.execute(text("ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS embedding vector(768)"))
    except Exception:
        pass
