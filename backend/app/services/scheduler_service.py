from __future__ import annotations

from datetime import date, datetime, timedelta
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import EmailStatus, Invoice, InvoiceStatus, ReminderEmail, Tone
from app.services.ai_service import recommend_follow_up_tone_with_context
from app.services.email_service import create_pending_reminder, retry_failed_emails, send_reminder_email
from app.time_utils import utcnow


def _automation_cadence() -> list[tuple[int, Tone]]:
    settings = get_settings()
    cadence = [
        (max(1, settings.auto_reminder_day_strict), Tone.STRICT),
        (max(1, settings.auto_reminder_day_professional), Tone.PROFESSIONAL),
        (max(1, settings.auto_reminder_day_friendly), Tone.FRIENDLY),
    ]
    # Evaluate most overdue stages first.
    cadence.sort(key=lambda item: item[0], reverse=True)
    return cadence


def run_automation_cycle(db: Session) -> dict[str, int]:
    settings = get_settings()
    cadence = _automation_cadence()
    today = date.today()
    cutoff = utcnow() - timedelta(days=max(0, settings.auto_reminder_min_days_since_last))

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
            select(ReminderEmail).where(ReminderEmail.invoice_id == invoice.id).order_by(ReminderEmail.created_at.desc())
        )
        if recent_reminder and recent_reminder.created_at >= cutoff:
            skipped_recent += 1
            continue

        sent_tones = {
            reminder_tone
            for reminder_tone, in db.execute(select(ReminderEmail.tone).where(ReminderEmail.invoice_id == invoice.id)).all()
        }

        next_tone: Tone | None = None
        for threshold_day, threshold_tone in cadence:
            if overdue_days >= threshold_day and threshold_tone not in sent_tones:
                next_tone = threshold_tone
                break

        if next_tone is None:
            skipped_no_stage_due += 1
            continue

        selected_tone, rationale, factors = recommend_follow_up_tone_with_context(db, invoice, fallback_tone=next_tone)
        reminder = create_pending_reminder(db, invoice, selected_tone, invoice.user_id, invoice.company_id)
        reminder.tone_rationale = f"Automation: {rationale}"
        reminder.tone_factors_json = json.dumps({**factors, "automation_baseline_tone": next_tone.value})
        db.commit()
        db.refresh(reminder)
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
