from datetime import date, datetime, timedelta
from email.message import EmailMessage
import smtplib
import json
import secrets

import httpx

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.config import get_settings
from app.models import EmailStatus, Invoice, InvoiceStatus, ReminderEmail, Tone


AUTOMATION_CADENCE: list[tuple[int, Tone]] = [
    (1, Tone.FRIENDLY),
    (7, Tone.PROFESSIONAL),
    (14, Tone.STRICT),
]


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
    invoice.paid_at = datetime.utcnow()
    db.commit()
    db.refresh(invoice)
    return invoice


def generate_email_content(invoice: Invoice, tone: Tone) -> tuple[str, str]:
    subject = f"Payment Reminder: Invoice #{invoice.id} - ${invoice.amount:,.2f}"
    payment_link = build_payment_link(invoice)

    if tone == Tone.FRIENDLY:
        body = (
            f"Hi {invoice.customer_name},\n\n"
            f"I hope you are doing well. This is a friendly reminder that an invoice of ${invoice.amount:,.2f} "
            f"was due on {invoice.due_date}.\n\n"
            f"You can complete payment securely here: {payment_link}\n\n"
            "If you have already made the payment, please ignore this message. "
            "Otherwise, we would appreciate it if you could process it at your earliest convenience.\n\n"
            "Thanks so much!"
        )
    elif tone == Tone.STRICT:
        body = (
            f"Dear {invoice.customer_name},\n\n"
            f"Your invoice payment of ${invoice.amount:,.2f}, due on {invoice.due_date}, is overdue.\n\n"
            f"Payment link: {payment_link}\n\n"
            "Immediate action is required. Please settle the outstanding amount without further delay.\n\n"
            "If payment has already been made, provide confirmation."
        )
    else:
        body = (
            f"Dear {invoice.customer_name},\n\n"
            f"This is a reminder regarding the outstanding invoice amount of ${invoice.amount:,.2f}, "
            f"which was due on {invoice.due_date}.\n\n"
            f"You can pay online using this link: {payment_link}\n\n"
            "Please arrange payment at your earliest convenience. "
            "If you have already completed the payment, kindly disregard this reminder.\n\n"
            "Best regards,\nAccounts Team"
        )

    return subject, body


def generate_email_content_with_ai(invoice: Invoice, tone: Tone) -> tuple[str, str]:
    settings = get_settings()
    if not settings.openai_api_key:
        return generate_email_content(invoice, tone)

    system_prompt = (
        "You generate concise and effective invoice payment reminder emails. "
        "Return a strict JSON object with keys: subject, body. "
        "Do not include markdown, code fences, or extra keys."
    )

    user_prompt = (
        f"Customer Name: {invoice.customer_name}\n"
        f"Invoice ID: {invoice.id}\n"
        f"Amount: ${invoice.amount:,.2f}\n"
        f"Due Date: {invoice.due_date}\n"
        f"Payment Link: {build_payment_link(invoice)}\n"
        f"Tone: {tone.value}\n"
        "Generate a payment reminder email."
    )

    payload = {
        "model": settings.openai_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.4,
    }

    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                f"{settings.openai_base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            subject = str(parsed["subject"]).strip()
            body = str(parsed["body"]).strip()

            if not subject or not body:
                return generate_email_content(invoice, tone)

            if "http" not in body.lower():
                body = f"{body}\n\nPay here: {build_payment_link(invoice)}"

            return subject, body
    except Exception:
        return generate_email_content(invoice, tone)


def create_pending_reminder(
    db: Session,
    invoice: Invoice,
    tone: Tone,
    user_id: int | None,
    company_id: int | None,
) -> ReminderEmail:
    subject, body = generate_email_content_with_ai(invoice, tone)
    reminder = ReminderEmail(
        user_id=user_id,
        company_id=company_id,
        invoice_id=invoice.id,
        subject=subject,
        body=body,
        tone=tone,
        status=EmailStatus.PENDING_APPROVAL,
    )
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return reminder


def send_with_smtp(
    to_email: str,
    subject: str,
    body: str,
    tracking_pixel_url: str,
) -> tuple[bool, str | None]:
    settings = get_settings()

    if settings.dry_run_email:
        return True, None

    try:
        msg = EmailMessage()
        msg["From"] = settings.smtp_from or settings.smtp_username
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)
        msg.add_alternative(
            (
                f"<html><body><p>{body.replace(chr(10), '<br/>')}</p>"
                f"<img src=\"{tracking_pixel_url}\" width=\"1\" height=\"1\" alt=\"\" />"
                "</body></html>"
            ),
            subtype="html",
        )

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(msg)

        return True, None
    except Exception as exc:
        return False, str(exc)


def send_reminder_email(db: Session, reminder: ReminderEmail, provider: str = "smtp") -> ReminderEmail:
    invoice = db.get(Invoice, reminder.invoice_id)
    if not invoice:
        reminder.status = EmailStatus.FAILED
        reminder.failure_reason = "Related invoice not found"
        db.commit()
        db.refresh(reminder)
        return reminder

    success = False
    error_message = None
    now = datetime.utcnow()

    if not reminder.tracking_token:
        reminder.tracking_token = secrets.token_urlsafe(18)

    tracking_base = get_settings().tracking_base_url.rstrip("/")
    tracking_pixel_url = f"{tracking_base}/emails/track/open/{reminder.tracking_token}.gif"

    reminder.retry_count = int(reminder.retry_count or 0) + 1
    reminder.last_attempt_at = now

    if provider == "gmail_api":
        success = True
    else:
        success, error_message = send_with_smtp(
            invoice.customer_email,
            reminder.subject,
            reminder.body,
            tracking_pixel_url,
        )

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

    failed_emails = db.scalars(
        select(ReminderEmail).where(ReminderEmail.status == EmailStatus.FAILED)
    ).all()

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


def run_automation_cycle(db: Session) -> dict[str, int]:
    settings = get_settings()
    today = date.today()
    cutoff = datetime.utcnow() - timedelta(days=max(0, settings.auto_reminder_min_days_since_last))

    overdue_invoices = db.scalars(
        select(Invoice).where(Invoice.status == InvoiceStatus.PENDING, Invoice.due_date < today)
    ).all()

    created_pending = 0
    auto_sent = 0
    skipped_recent = 0
    skipped_no_stage_due = 0

    for invoice in overdue_invoices:
        overdue_days = (today - invoice.due_date).days
        if overdue_days < 1:
            skipped_no_stage_due += 1
            continue

        recent_reminder = db.scalar(
            select(ReminderEmail)
            .where(ReminderEmail.invoice_id == invoice.id)
            .order_by(ReminderEmail.created_at.desc())
        )

        if recent_reminder and recent_reminder.created_at >= cutoff:
            skipped_recent += 1
            continue

        sent_tones = {
            reminder_tone
            for reminder_tone, in db.execute(
                select(ReminderEmail.tone).where(ReminderEmail.invoice_id == invoice.id)
            ).all()
        }

        next_tone: Tone | None = None
        for threshold_day, threshold_tone in AUTOMATION_CADENCE:
            if overdue_days >= threshold_day and threshold_tone not in sent_tones:
                next_tone = threshold_tone
                break

        if next_tone is None:
            skipped_no_stage_due += 1
            continue

        reminder = create_pending_reminder(db, invoice, next_tone, invoice.user_id, invoice.company_id)
        created_pending += 1

        if settings.auto_send_without_approval:
            reminder.status = EmailStatus.APPROVED
            db.commit()
            db.refresh(reminder)
            sent_result = send_reminder_email(db, reminder, "smtp")
            if sent_result.status in {EmailStatus.SENT, EmailStatus.DELIVERED, EmailStatus.OPENED}:
                auto_sent += 1

    retry_summary = retry_failed_emails(db)

    return {
        "overdue_checked": len(overdue_invoices),
        "created_pending": created_pending,
        "auto_sent": auto_sent,
        "skipped_recent": skipped_recent,
        "skipped_no_stage_due": skipped_no_stage_due,
        "retried_failed": retry_summary["retried"],
    }
