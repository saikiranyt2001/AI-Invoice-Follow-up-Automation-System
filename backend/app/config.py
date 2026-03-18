from functools import lru_cache
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import secrets

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
    auth_secret_key: str = os.getenv("AUTH_SECRET_KEY") or secrets.token_urlsafe(48)
    auth_algorithm: str = os.getenv("AUTH_ALGORITHM", "HS256")
    auth_access_token_minutes: int = int(os.getenv("AUTH_ACCESS_TOKEN_MINUTES", "1440"))
    payment_link_base_url: str = os.getenv("PAYMENT_LINK_BASE_URL", "http://127.0.0.1:8000/payments/pay")
    automation_enabled: bool = os.getenv("AUTOMATION_ENABLED", "true").lower() == "true"
    automation_interval_minutes: int = int(os.getenv("AUTOMATION_INTERVAL_MINUTES", "60"))
    auto_send_without_approval: bool = os.getenv("AUTO_SEND_WITHOUT_APPROVAL", "true").lower() == "true"
    auto_reminder_tone: str = os.getenv("AUTO_REMINDER_TONE", "professional").lower()
    auto_reminder_min_days_since_last: int = int(os.getenv("AUTO_REMINDER_MIN_DAYS_SINCE_LAST", "3"))
    tracking_base_url: str = os.getenv("TRACKING_BASE_URL", "http://127.0.0.1:8000")
    max_email_retries: int = int(os.getenv("MAX_EMAIL_RETRIES", "3"))
    retry_delay_minutes: int = int(os.getenv("RETRY_DELAY_MINUTES", "15"))
    integration_redirect_base_url: str = os.getenv("INTEGRATION_REDIRECT_BASE_URL", "http://127.0.0.1:5173/integrations/callback")
    xero_client_id: str = os.getenv("XERO_CLIENT_ID", "")
    quickbooks_client_id: str = os.getenv("QUICKBOOKS_CLIENT_ID", "")
    quickbooks_client_secret: str = os.getenv("QUICKBOOKS_CLIENT_SECRET", "")
    quickbooks_auth_url: str = os.getenv("QUICKBOOKS_AUTH_URL", "https://appcenter.intuit.com/connect/oauth2")
    quickbooks_token_url: str = os.getenv("QUICKBOOKS_TOKEN_URL", "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer")
    quickbooks_scope: str = os.getenv("QUICKBOOKS_SCOPE", "com.intuit.quickbooks.accounting")
    zoho_books_client_id: str = os.getenv("ZOHO_BOOKS_CLIENT_ID", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
