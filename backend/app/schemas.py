from datetime import date, datetime
from pydantic import BaseModel, EmailStr, Field

from app.models import EmailStatus, InvoiceStatus, Tone, UserRole


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    otp_code: str | None = Field(default=None, min_length=6, max_length=8)


class UserOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    role: UserRole
    active_company_id: int | None = None
    mfa_enabled: bool = False

    class Config:
        from_attributes = True


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    user: UserOut


class TokenRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=255)


class LogoutRequest(BaseModel):
    refresh_token: str | None = Field(default=None, min_length=20, max_length=255)


class MfaSetupOut(BaseModel):
    secret: str
    otpauth_uri: str


class MfaEnableRequest(BaseModel):
    otp_code: str = Field(min_length=6, max_length=8)


class TeamMemberCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.TEAM


class IntegrationImportRequest(BaseModel):
    source: str = Field(pattern="^(fake_api|xero|quickbooks|zoho_books)$")
    count: int = Field(default=5, ge=1, le=50)


class IntegrationOAuthCallbackRequest(BaseModel):
    code: str = Field(min_length=3, max_length=255)
    state: str = Field(min_length=6, max_length=120)


class IntegrationSyncRequest(BaseModel):
    count: int = Field(default=5, ge=1, le=50)


class IntegrationOAuthStartOut(BaseModel):
    provider: str
    auth_url: str
    state: str


class IntegrationConnectorOut(BaseModel):
    provider: str
    display_name: str
    connected: bool
    mode: str
    auth_url: str
    last_synced_at: datetime | None
    last_error: str | None


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class CompanySwitchRequest(BaseModel):
    company_id: int = Field(gt=0)


class CompanyInviteRequest(BaseModel):
    email: EmailStr


class CompanyMemberRemoveRequest(BaseModel):
    user_id: int = Field(gt=0)


class CompanyOut(BaseModel):
    id: int
    owner_user_id: int
    name: str
    created_at: datetime

    class Config:
        from_attributes = True


class InvoiceCreate(BaseModel):
    customer_name: str = Field(min_length=1, max_length=120)
    customer_email: EmailStr
    customer_phone: str | None = Field(default=None, max_length=30)
    amount: float = Field(gt=0)
    due_date: date


class InvoiceOut(BaseModel):
    id: int
    customer_name: str
    customer_email: EmailStr
    customer_phone: str | None = None
    amount: float
    due_date: date
    status: InvoiceStatus
    is_overdue: bool
    payment_url: str | None = None
    payment_reference: str | None = None
    paid_at: datetime | None = None

    class Config:
        from_attributes = True


class InvoiceStatusUpdate(BaseModel):
    status: InvoiceStatus


class EmailGenerateRequest(BaseModel):
    invoice_id: int
    tone: Tone = Tone.PROFESSIONAL


class ReminderEmailUpdate(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)


class ReminderEmailOut(BaseModel):
    id: int
    invoice_id: int
    subject: str
    body: str
    tone: Tone
    channel: str
    status: EmailStatus
    failure_reason: str | None
    provider_message_id: str | None
    retry_count: int
    last_attempt_at: datetime | None
    sent_at: datetime | None
    delivered_at: datetime | None
    opened_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class DashboardStats(BaseModel):
    total_invoices: int
    overdue_invoices: int
    emails_sent: int
    pending_approvals: int


class LatePayerInsight(BaseModel):
    customer_name: str
    customer_email: EmailStr
    total_invoices: int
    overdue_invoices: int
    overdue_rate: float
    risk_level: str
    insight: str


class SendEmailRequest(BaseModel):
    provider: str = Field(default="smtp", pattern="^(smtp|gmail_api|twilio_sms)$")


class PaymentConfirmRequest(BaseModel):
    payment_reference: str = Field(min_length=3, max_length=255)


class CustomerHistoryTrendPoint(BaseModel):
    month: str
    risk_score: float


class CustomerHistoryOut(BaseModel):
    customer_name: str
    customer_email: EmailStr
    total_invoices: int
    paid_invoices: int
    overdue_invoices: int
    outstanding_amount: float
    on_time_payment_rate: float
    average_days_late: float
    risk_score: float
    risk_level: str
    trend: list[CustomerHistoryTrendPoint]


class AuditLogOut(BaseModel):
    id: int
    company_id: int | None
    user_id: int | None
    action: str
    entity_type: str
    entity_id: int | None
    details: dict[str, object]
    created_at: datetime


class JobQueueOut(BaseModel):
    id: int
    company_id: int | None
    user_id: int | None
    job_type: str
    payload: dict[str, object]
    status: str
    attempts: int
    max_attempts: int
    available_at: datetime
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class QueueStatsOut(BaseModel):
    queued: int
    processing: int
    succeeded: int
    failed: int


class PaymentWebhookIn(BaseModel):
    payment_reference: str = Field(min_length=3, max_length=255)
    invoice_id: int | None = Field(default=None, gt=0)
    payment_token: str | None = Field(default=None, min_length=6, max_length=255)
    idempotency_key: str = Field(min_length=6, max_length=140)
    source: str = Field(default="payment_gateway", min_length=2, max_length=60)


class EmailStatusWebhookIn(BaseModel):
    idempotency_key: str = Field(min_length=6, max_length=140)
    provider_message_id: str | None = Field(default=None, min_length=3, max_length=255)
    tracking_token: str | None = Field(default=None, min_length=6, max_length=255)
    status: str = Field(pattern="^(delivered|opened|failed)$")
    error_message: str | None = Field(default=None, max_length=500)
    source: str = Field(default="email_provider", min_length=2, max_length=60)


class WebhookAckOut(BaseModel):
    accepted: bool
    duplicate: bool
    event_key: str


class OpsMetricsOut(BaseModel):
    total_invoices: int
    overdue_invoices: int
    queued_jobs: int
    failed_jobs: int
    failed_emails: int
    webhook_events_24h: int
