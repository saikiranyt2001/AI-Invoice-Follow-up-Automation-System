from datetime import date, datetime
from enum import Enum

from sqlalchemy import Date, DateTime, Enum as SqlEnum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class InvoiceStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"


class EmailStatus(str, Enum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    SENT = "sent"
    FAILED = "failed"


class Tone(str, Enum):
    FRIENDLY = "friendly"
    PROFESSIONAL = "professional"
    STRICT = "strict"


class UserRole(str, Enum):
    ADMIN = "admin"
    TEAM = "team"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    role: Mapped[UserRole] = mapped_column(
        SqlEnum(UserRole, values_callable=lambda enum_cls: [member.value for member in enum_cls]),
        default=UserRole.TEAM,
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    customer_name: Mapped[str] = mapped_column(String(120), nullable=False)
    customer_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[InvoiceStatus] = mapped_column(SqlEnum(InvoiceStatus), default=InvoiceStatus.PENDING, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    reminders: Mapped[list["ReminderEmail"]] = relationship("ReminderEmail", back_populates="invoice", cascade="all, delete-orphan")


class ReminderEmail(Base):
    __tablename__ = "reminder_emails"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    tone: Mapped[Tone] = mapped_column(SqlEnum(Tone), default=Tone.PROFESSIONAL, nullable=False)
    status: Mapped[EmailStatus] = mapped_column(SqlEnum(EmailStatus), default=EmailStatus.PENDING_APPROVAL, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    invoice: Mapped[Invoice] = relationship("Invoice", back_populates="reminders")
