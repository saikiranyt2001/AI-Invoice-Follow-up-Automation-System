from datetime import date, datetime
from email.message import EmailMessage
import smtplib
import json

import httpx

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import EmailStatus, Invoice, InvoiceStatus, ReminderEmail, Tone


def is_overdue(invoice: Invoice) -> bool:
    return invoice.status == InvoiceStatus.PENDING and invoice.due_date < date.today()


def generate_email_content(invoice: Invoice, tone: Tone) -> tuple[str, str]:
    subject = f"Payment Reminder: Invoice #{invoice.id} - ${invoice.amount:,.2f}"

    if tone == Tone.FRIENDLY:
        body = (
            f"Hi {invoice.customer_name},\n\n"
            f"I hope you are doing well. This is a friendly reminder that an invoice of ${invoice.amount:,.2f} "
            f"was due on {invoice.due_date}.\n\n"
            "If you have already made the payment, please ignore this message. "
            "Otherwise, we would appreciate it if you could process it at your earliest convenience.\n\n"
            "Thanks so much!"
        )
    elif tone == Tone.STRICT:
        body = (
            f"Dear {invoice.customer_name},\n\n"
            f"Your invoice payment of ${invoice.amount:,.2f}, due on {invoice.due_date}, is overdue.\n\n"
            "Immediate action is required. Please settle the outstanding amount without further delay.\n\n"
            "If payment has already been made, provide confirmation."
        )
    else:
        body = (
            f"Dear {invoice.customer_name},\n\n"
            f"This is a reminder regarding the outstanding invoice amount of ${invoice.amount:,.2f}, "
            f"which was due on {invoice.due_date}.\n\n"
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

            return subject, body
    except Exception:
        return generate_email_content(invoice, tone)


def create_pending_reminder(db: Session, invoice: Invoice, tone: Tone, user_id: int) -> ReminderEmail:
    subject, body = generate_email_content_with_ai(invoice, tone)
    reminder = ReminderEmail(
        user_id=user_id,
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


def send_with_smtp(to_email: str, subject: str, body: str) -> tuple[bool, str | None]:
    settings = get_settings()

    if settings.dry_run_email:
        return True, None

    try:
        msg = EmailMessage()
        msg["From"] = settings.smtp_from or settings.smtp_username
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)

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

    if provider == "gmail_api":
        success = True
    else:
        success, error_message = send_with_smtp(invoice.customer_email, reminder.subject, reminder.body)

    if success:
        reminder.status = EmailStatus.SENT
        reminder.failure_reason = None
        reminder.sent_at = datetime.utcnow()
    else:
        reminder.status = EmailStatus.FAILED
        reminder.failure_reason = error_message or "Unknown email sending error"

    db.commit()
    db.refresh(reminder)
    return reminder
