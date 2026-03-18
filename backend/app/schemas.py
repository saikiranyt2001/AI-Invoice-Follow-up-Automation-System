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
    source: str = Field(pattern="^(fake_api|xero|quickbooks)$")
    count: int = Field(default=5, ge=1, le=50)


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
    sent_at: datetime | None
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
