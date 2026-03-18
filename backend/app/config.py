from functools import lru_cache
from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()


class Settings(BaseModel):
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./invoice_automation.db")
    smtp_host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: str = os.getenv("SMTP_USERNAME", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_from: str = os.getenv("SMTP_FROM", "")
    dry_run_email: bool = os.getenv("DRY_RUN_EMAIL", "true").lower() == "true"
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    auth_secret_key: str = os.getenv("AUTH_SECRET_KEY", "change-me-in-production")
    auth_algorithm: str = os.getenv("AUTH_ALGORITHM", "HS256")
    auth_access_token_minutes: int = int(os.getenv("AUTH_ACCESS_TOKEN_MINUTES", "1440"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
