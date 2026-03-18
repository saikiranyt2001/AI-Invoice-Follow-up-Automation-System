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
        user_columns = {col["name"] for col in inspector.get_columns("users")}
        invoice_columns = {col["name"] for col in inspector.get_columns("invoices")}
        reminder_columns = {col["name"] for col in inspector.get_columns("reminder_emails")}

        if "role" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(20)"))
            connection.execute(text("UPDATE users SET role = 'team' WHERE role IS NULL"))
        else:
            connection.execute(text("UPDATE users SET role = lower(role) WHERE role IS NOT NULL"))
            connection.execute(text("UPDATE users SET role = 'team' WHERE role IS NULL OR role = ''"))

        if "user_id" not in invoice_columns:
            connection.execute(text("ALTER TABLE invoices ADD COLUMN user_id INTEGER"))

        if "user_id" not in reminder_columns:
            connection.execute(text("ALTER TABLE reminder_emails ADD COLUMN user_id INTEGER"))
