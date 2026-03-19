from __future__ import annotations

from datetime import date, datetime
import secrets

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Invoice, InvoiceStatus
from app.time_utils import utcnow


def is_overdue(invoice: Invoice) -> bool:
    return invoice.status == InvoiceStatus.PENDING and invoice.due_date < date.today()


def build_payment_link(invoice: Invoice) -> str:
    if not invoice.payment_token:
        invoice.payment_token = secrets.token_urlsafe(18)
    settings = get_settings()
    base = settings.payment_link_base_url.rstrip("/")
    return f"{base}/{invoice.payment_token}?invoice_id={invoice.id}&amount={invoice.amount:.2f}"


def ensure_payment_token(db: Session, invoice: Invoice) -> str:
    if not invoice.payment_token:
        invoice.payment_token = secrets.token_urlsafe(18)
        db.commit()
        db.refresh(invoice)
    return invoice.payment_token


def build_payment_link_by_token(token: str) -> str:
    settings = get_settings()
    base = settings.payment_link_base_url.rstrip("/")
    return f"{base}/{token}"


def mark_invoice_paid(db: Session, invoice: Invoice, payment_reference: str) -> Invoice:
    if invoice.status == InvoiceStatus.PAID:
        return invoice

    invoice.status = InvoiceStatus.PAID
    invoice.payment_reference = payment_reference.strip()
    invoice.paid_at = utcnow()
    db.commit()
    db.refresh(invoice)
    return invoice
