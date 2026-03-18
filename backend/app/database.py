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

        if "user_id" not in invoice_columns:
            connection.execute(text("ALTER TABLE invoices ADD COLUMN user_id INTEGER"))

        if "company_id" not in invoice_columns:
            connection.execute(text("ALTER TABLE invoices ADD COLUMN company_id INTEGER"))

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
