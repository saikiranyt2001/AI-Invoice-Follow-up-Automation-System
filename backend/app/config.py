import os
import secrets
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()


class Settings(BaseModel):
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./invoice_automation.db")
    smtp_host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: str = os.getenv("SMTP_USERNAME", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_from: str = os.getenv("SMTP_FROM", "")
    gmail_access_token: str = os.getenv("GMAIL_ACCESS_TOKEN", "")
    gmail_from_email: str = os.getenv("GMAIL_FROM_EMAIL", "")
    dry_run_email: bool = os.getenv("DRY_RUN_EMAIL", "true").lower() == "true"
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    openai_message_generation_enabled: bool = (
        os.getenv("OPENAI_MESSAGE_GENERATION_ENABLED", "true").lower() == "true"
    )
    sendgrid_api_key: str = os.getenv("SENDGRID_API_KEY", "")
    sendgrid_from_email: str = os.getenv("SENDGRID_FROM_EMAIL", "")
    auth_secret_key: str = os.getenv("AUTH_SECRET_KEY") or secrets.token_urlsafe(48)
    auth_algorithm: str = os.getenv("AUTH_ALGORITHM", "HS256")
    auth_access_token_minutes: int = int(os.getenv("AUTH_ACCESS_TOKEN_MINUTES", "1440"))
    auth_refresh_token_days: int = int(os.getenv("AUTH_REFRESH_TOKEN_DAYS", "30"))
    payment_provider: str = os.getenv("PAYMENT_PROVIDER", "internal").lower()
    payment_link_base_url: str = os.getenv(
        "PAYMENT_LINK_BASE_URL", "http://127.0.0.1:8000/payments/pay"
    )
    stripe_payment_link_base_url: str = os.getenv(
        "STRIPE_PAYMENT_LINK_BASE_URL", "https://buy.stripe.com/test_example"
    )
    razorpay_payment_link_base_url: str = os.getenv(
        "RAZORPAY_PAYMENT_LINK_BASE_URL", "https://rzp.io/l/test-example"
    )
    automation_enabled: bool = os.getenv("AUTOMATION_ENABLED", "true").lower() == "true"
    automation_interval_minutes: int = int(os.getenv("AUTOMATION_INTERVAL_MINUTES", "60"))
    auto_send_without_approval: bool = (
        os.getenv("AUTO_SEND_WITHOUT_APPROVAL", "true").lower() == "true"
    )
    auto_reminder_tone: str = os.getenv("AUTO_REMINDER_TONE", "professional").lower()
    auto_reminder_min_days_since_last: int = int(
        os.getenv("AUTO_REMINDER_MIN_DAYS_SINCE_LAST", "3")
    )
    auto_followup_channels: str = os.getenv(
        "AUTO_FOLLOWUP_CHANNELS", "smtp,twilio_whatsapp,twilio_sms"
    )
    auto_reminder_day_friendly: int = int(os.getenv("AUTO_REMINDER_DAY_FRIENDLY", "1"))
    auto_reminder_day_professional: int = int(os.getenv("AUTO_REMINDER_DAY_PROFESSIONAL", "5"))
    auto_reminder_day_strict: int = int(os.getenv("AUTO_REMINDER_DAY_STRICT", "10"))
    tracking_base_url: str = os.getenv("TRACKING_BASE_URL", "http://127.0.0.1:8000")
    max_email_retries: int = int(os.getenv("MAX_EMAIL_RETRIES", "3"))
    retry_delay_minutes: int = int(os.getenv("RETRY_DELAY_MINUTES", "15"))
    sms_enabled: bool = os.getenv("SMS_ENABLED", "false").lower() == "true"
    sms_provider: str = os.getenv("SMS_PROVIDER", "twilio_sms")
    sms_dry_run: bool = os.getenv("SMS_DRY_RUN", "true").lower() == "true"
    twilio_account_sid: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    twilio_auth_token: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    twilio_from_number: str = os.getenv("TWILIO_FROM_NUMBER", "")
    twilio_whatsapp_from_number: str = os.getenv("TWILIO_WHATSAPP_FROM_NUMBER", "")
    webhook_shared_secret: str = os.getenv("WEBHOOK_SHARED_SECRET", "")
    redis_url: str = os.getenv("REDIS_URL", "")
    rate_limit_window_seconds: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
    rate_limit_requests: int = int(os.getenv("RATE_LIMIT_REQUESTS", "120"))
    auth_rate_limit_requests: int = int(os.getenv("AUTH_RATE_LIMIT_REQUESTS", "20"))
    integration_redirect_base_url: str = os.getenv(
        "INTEGRATION_REDIRECT_BASE_URL", "http://127.0.0.1:5173/integrations/callback"
    )
    xero_client_id: str = os.getenv("XERO_CLIENT_ID", "")
    quickbooks_client_id: str = os.getenv("QUICKBOOKS_CLIENT_ID", "")
    quickbooks_client_secret: str = os.getenv("QUICKBOOKS_CLIENT_SECRET", "")
    quickbooks_auth_url: str = os.getenv(
        "QUICKBOOKS_AUTH_URL", "https://appcenter.intuit.com/connect/oauth2"
    )
    quickbooks_token_url: str = os.getenv(
        "QUICKBOOKS_TOKEN_URL", "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
    )
    quickbooks_scope: str = os.getenv("QUICKBOOKS_SCOPE", "com.intuit.quickbooks.accounting")
    zoho_books_client_id: str = os.getenv("ZOHO_BOOKS_CLIENT_ID", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
