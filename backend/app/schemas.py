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


class UserOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    role: UserRole
    active_company_id: int | None = None

    class Config:
        from_attributes = True


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


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
    amount: float = Field(gt=0)
    due_date: date


class InvoiceOut(BaseModel):
    id: int
    customer_name: str
    customer_email: EmailStr
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
    provider: str = Field(default="smtp", pattern="^(smtp|gmail_api)$")


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
