from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_lightweight_migrations() -> None:
    inspector = inspect(engine)

    if "users" not in inspector.get_table_names():
        return

    with engine.begin() as connection:
        table_names = set(inspector.get_table_names())
        user_columns = {col["name"] for col in inspector.get_columns("users")}
        invoice_columns = {col["name"] for col in inspector.get_columns("invoices")}
        reminder_columns = {col["name"] for col in inspector.get_columns("reminder_emails")}

        if "company_memberships" not in table_names:
            connection.execute(
                text(
                    "CREATE TABLE company_memberships ("
                    "id INTEGER PRIMARY KEY, "
                    "company_id INTEGER NOT NULL, "
                    "user_id INTEGER NOT NULL, "
                    "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
                    ")"
                )
            )
            connection.execute(text("CREATE UNIQUE INDEX uq_company_member ON company_memberships(company_id, user_id)"))

        if "integration_connections" not in table_names:
            connection.execute(
                text(
                    "CREATE TABLE integration_connections ("
                    "id INTEGER PRIMARY KEY, "
                    "company_id INTEGER NOT NULL, "
                    "provider VARCHAR(40) NOT NULL, "
                    "connected INTEGER NOT NULL DEFAULT 0, "
                    "oauth_state VARCHAR(80), "
                    "access_token VARCHAR(255), "
                    "refresh_token VARCHAR(255), "
                    "last_error TEXT, "
                    "last_synced_at DATETIME, "
                    "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                    "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
                    ")"
                )
            )
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX uq_integration_connection "
                    "ON integration_connections(company_id, provider)"
                )
            )

        if "audit_logs" not in table_names:
            connection.execute(
                text(
                    "CREATE TABLE audit_logs ("
                    "id INTEGER PRIMARY KEY, "
                    "company_id INTEGER, "
                    "user_id INTEGER, "
                    "action VARCHAR(80) NOT NULL, "
                    "entity_type VARCHAR(80) NOT NULL, "
                    "entity_id INTEGER, "
                    "details_json TEXT, "
                    "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
                    ")"
                )
            )
            connection.execute(text("CREATE INDEX ix_audit_logs_company_id ON audit_logs(company_id)"))
            connection.execute(text("CREATE INDEX ix_audit_logs_created_at ON audit_logs(created_at)"))

        if "job_queue" not in table_names:
            connection.execute(
                text(
                    "CREATE TABLE job_queue ("
                    "id INTEGER PRIMARY KEY, "
                    "company_id INTEGER, "
                    "user_id INTEGER, "
                    "job_type VARCHAR(60) NOT NULL, "
                    "payload_json TEXT NOT NULL DEFAULT '{}', "
                    "status VARCHAR(20) NOT NULL DEFAULT 'queued', "
                    "attempts INTEGER NOT NULL DEFAULT 0, "
                    "max_attempts INTEGER NOT NULL DEFAULT 3, "
                    "available_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                    "last_error TEXT, "
                    "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                    "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
                    ")"
                )
            )
            connection.execute(text("CREATE INDEX ix_job_queue_status ON job_queue(status)"))
            connection.execute(text("CREATE INDEX ix_job_queue_available_at ON job_queue(available_at)"))

        if "webhook_events" not in table_names:
            connection.execute(
                text(
                    "CREATE TABLE webhook_events ("
                    "id INTEGER PRIMARY KEY, "
                    "source VARCHAR(60) NOT NULL, "
                    "event_type VARCHAR(60) NOT NULL, "
                    "event_key VARCHAR(140) NOT NULL, "
                    "payload_json TEXT NOT NULL DEFAULT '{}', "
                    "processed INTEGER NOT NULL DEFAULT 1, "
                    "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
                    ")"
                )
            )
            connection.execute(text("CREATE UNIQUE INDEX uq_webhook_event_key ON webhook_events(event_key)"))
            connection.execute(text("CREATE INDEX ix_webhook_events_source ON webhook_events(source)"))
            connection.execute(text("CREATE INDEX ix_webhook_events_created_at ON webhook_events(created_at)"))

        if "refresh_tokens" not in table_names:
            connection.execute(
                text(
                    "CREATE TABLE refresh_tokens ("
                    "id INTEGER PRIMARY KEY, "
                    "user_id INTEGER NOT NULL, "
                    "token_hash VARCHAR(128) NOT NULL UNIQUE, "
                    "expires_at DATETIME NOT NULL, "
                    "revoked INTEGER NOT NULL DEFAULT 0, "
                    "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
                    ")"
                )
            )
            connection.execute(text("CREATE INDEX ix_refresh_tokens_user_id ON refresh_tokens(user_id)"))
            connection.execute(text("CREATE INDEX ix_refresh_tokens_expires_at ON refresh_tokens(expires_at)"))

        if "revoked_access_tokens" not in table_names:
            connection.execute(
                text(
                    "CREATE TABLE revoked_access_tokens ("
                    "id INTEGER PRIMARY KEY, "
                    "jti VARCHAR(80) NOT NULL UNIQUE, "
                    "expires_at DATETIME NOT NULL, "
                    "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
                    ")"
                )
            )
            connection.execute(text("CREATE INDEX ix_revoked_access_tokens_expires_at ON revoked_access_tokens(expires_at)"))

        if "role" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(20)"))
            connection.execute(text("UPDATE users SET role = 'team' WHERE role IS NULL"))
        else:
            connection.execute(text("UPDATE users SET role = lower(role) WHERE role IS NOT NULL"))
            connection.execute(text("UPDATE users SET role = 'team' WHERE role IS NULL OR role = ''"))
            connection.execute(
                text(
                    "UPDATE users SET role = 'team' "
                    "WHERE role NOT IN ('admin', 'manager', 'accountant', 'team')"
                )
            )

        if "active_company_id" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN active_company_id INTEGER"))

        if "mfa_enabled" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN mfa_enabled INTEGER DEFAULT 0"))
            connection.execute(text("UPDATE users SET mfa_enabled = 0 WHERE mfa_enabled IS NULL"))

        if "mfa_secret" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN mfa_secret VARCHAR(64)"))

        if "user_id" not in invoice_columns:
            connection.execute(text("ALTER TABLE invoices ADD COLUMN user_id INTEGER"))

        if "company_id" not in invoice_columns:
            connection.execute(text("ALTER TABLE invoices ADD COLUMN company_id INTEGER"))

        if "customer_phone" not in invoice_columns:
            connection.execute(text("ALTER TABLE invoices ADD COLUMN customer_phone VARCHAR(30)"))

        if "payment_token" not in invoice_columns:
            connection.execute(text("ALTER TABLE invoices ADD COLUMN payment_token VARCHAR(128)"))

        if "payment_reference" not in invoice_columns:
            connection.execute(text("ALTER TABLE invoices ADD COLUMN payment_reference VARCHAR(255)"))

        if "paid_at" not in invoice_columns:
            connection.execute(text("ALTER TABLE invoices ADD COLUMN paid_at DATETIME"))

        if "user_id" not in reminder_columns:
            connection.execute(text("ALTER TABLE reminder_emails ADD COLUMN user_id INTEGER"))

        if "company_id" not in reminder_columns:
            connection.execute(text("ALTER TABLE reminder_emails ADD COLUMN company_id INTEGER"))

        if "provider_message_id" not in reminder_columns:
            connection.execute(text("ALTER TABLE reminder_emails ADD COLUMN provider_message_id VARCHAR(255)"))

        if "channel" not in reminder_columns:
            connection.execute(text("ALTER TABLE reminder_emails ADD COLUMN channel VARCHAR(20) DEFAULT 'email'"))
            connection.execute(text("UPDATE reminder_emails SET channel = 'email' WHERE channel IS NULL OR channel = ''"))

        if "tracking_token" not in reminder_columns:
            connection.execute(text("ALTER TABLE reminder_emails ADD COLUMN tracking_token VARCHAR(128)"))

        if "retry_count" not in reminder_columns:
            connection.execute(text("ALTER TABLE reminder_emails ADD COLUMN retry_count INTEGER DEFAULT 0"))
            connection.execute(text("UPDATE reminder_emails SET retry_count = 0 WHERE retry_count IS NULL"))

        if "last_attempt_at" not in reminder_columns:
            connection.execute(text("ALTER TABLE reminder_emails ADD COLUMN last_attempt_at DATETIME"))

        if "delivered_at" not in reminder_columns:
            connection.execute(text("ALTER TABLE reminder_emails ADD COLUMN delivered_at DATETIME"))

        if "opened_at" not in reminder_columns:
            connection.execute(text("ALTER TABLE reminder_emails ADD COLUMN opened_at DATETIME"))
