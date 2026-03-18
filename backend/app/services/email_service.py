from __future__ import annotations

from datetime import datetime, timedelta
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.email.sender import send_reminder_via_provider
from app.models import EmailStatus, Invoice, ReminderEmail, Tone
from app.services.ai_service import generate_reminder_content
from app.services.invoice_service import build_payment_link


def create_pending_reminder(
    db: Session,
    invoice: Invoice,
    tone: Tone,
    user_id: int | None,
    company_id: int | None,
    message_style: str | None = None,
) -> ReminderEmail:
    payment_link = build_payment_link(invoice)
    subject, body = generate_reminder_content(invoice, tone, payment_link, message_style)
    reminder = ReminderEmail(
        user_id=user_id,
        company_id=company_id,
        invoice_id=invoice.id,
        subject=subject,
        body=body,
        tone=tone,
        channel="email",
        status=EmailStatus.PENDING_APPROVAL,
    )
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return reminder


def send_reminder_email(db: Session, reminder: ReminderEmail, provider: str = "smtp") -> ReminderEmail:
    invoice = db.get(Invoice, reminder.invoice_id)
    if not invoice:
        reminder.status = EmailStatus.FAILED
        reminder.failure_reason = "Related invoice not found"
        db.commit()
        db.refresh(reminder)
        return reminder

    now = datetime.utcnow()

    if not reminder.tracking_token:
        reminder.tracking_token = secrets.token_urlsafe(18)

    tracking_base = get_settings().tracking_base_url.rstrip("/")
    tracking_pixel_url = f"{tracking_base}/emails/track/open/{reminder.tracking_token}.gif"

    reminder.retry_count = int(reminder.retry_count or 0) + 1
    reminder.last_attempt_at = now

    recipient_hint = getattr(invoice, "customer_phone", "") or invoice.customer_email
    outbound_body = reminder.body
    if provider == "twilio_sms":
        outbound_body = f"Invoice #{invoice.id} overdue. Pay: {build_payment_link(invoice)}"

    success, error_message, channel = send_reminder_via_provider(
        provider=provider,
        to_email=invoice.customer_email,
        recipient_hint=recipient_hint,
        subject=reminder.subject,
        body=outbound_body,
        tracking_pixel_url=tracking_pixel_url,
    )
    reminder.channel = channel

    if success:
        reminder.provider_message_id = f"msg_{secrets.token_hex(8)}"
        reminder.status = EmailStatus.DELIVERED
        reminder.failure_reason = None
        reminder.sent_at = now
        reminder.delivered_at = now
    else:
        reminder.status = EmailStatus.FAILED
        reminder.failure_reason = error_message or "Unknown email sending error"

    db.commit()
    db.refresh(reminder)
    return reminder


def mark_email_opened(db: Session, token: str) -> ReminderEmail | None:
    reminder = db.scalar(select(ReminderEmail).where(ReminderEmail.tracking_token == token))
    if not reminder:
        return None

    if reminder.opened_at is None:
        reminder.opened_at = datetime.utcnow()
    reminder.status = EmailStatus.OPENED

    db.commit()
    db.refresh(reminder)
    return reminder


def retry_failed_emails(db: Session) -> dict[str, int]:
    settings = get_settings()
    min_next_attempt = datetime.utcnow() - timedelta(minutes=max(1, settings.retry_delay_minutes))

    failed_emails = db.scalars(select(ReminderEmail).where(ReminderEmail.status == EmailStatus.FAILED)).all()

    retried = 0
    skipped_retry_limit = 0
    skipped_retry_delay = 0

    for reminder in failed_emails:
        if int(reminder.retry_count or 0) >= max(1, settings.max_email_retries):
            skipped_retry_limit += 1
            continue
        if reminder.last_attempt_at and reminder.last_attempt_at > min_next_attempt:
            skipped_retry_delay += 1
            continue
        send_reminder_email(db, reminder, "smtp")
        retried += 1

    return {
        "failed_found": len(failed_emails),
        "retried": retried,
        "skipped_retry_limit": skipped_retry_limit,
        "skipped_retry_delay": skipped_retry_delay,
    }
