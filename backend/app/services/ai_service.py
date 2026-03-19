from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.email.templates import generate_email_content_with_ai
from app.models import Invoice, InvoiceStatus, Tone


_TONE_SCORE = {
    Tone.FRIENDLY: 1,
    Tone.PROFESSIONAL: 2,
    Tone.STRICT: 3,
}


def generate_reminder_content(
    invoice: Invoice,
    tone: Tone,
    payment_link: str,
    message_style: str | None = None,
) -> tuple[str, str]:
    return generate_email_content_with_ai(invoice, tone, payment_link, message_style)


def recommend_follow_up_tone(db: Session, invoice: Invoice, fallback_tone: Tone | None = None) -> Tone:
    today = date.today()
    delay_days = max(0, (today - invoice.due_date).days)

    history = db.scalars(
        select(Invoice)
        .where(
            Invoice.customer_email == invoice.customer_email,
            Invoice.company_id == invoice.company_id,
        )
        .order_by(Invoice.created_at.asc())
    ).all()

    total = len(history)
    late_or_overdue = 0
    for item in history:
        if item.status == InvoiceStatus.PENDING and item.due_date < today:
            late_or_overdue += 1
        elif item.status == InvoiceStatus.PAID and item.paid_at and item.paid_at.date() > item.due_date:
            late_or_overdue += 1

    late_rate = (late_or_overdue / total) if total else 0.0

    recommended = Tone.FRIENDLY
    if delay_days >= 10 or invoice.amount >= 5000 or late_rate >= 0.6:
        recommended = Tone.STRICT
    elif delay_days >= 5 or invoice.amount >= 1500 or late_rate >= 0.3:
        recommended = Tone.PROFESSIONAL

    if not fallback_tone:
        return recommended
    return recommended if _TONE_SCORE[recommended] >= _TONE_SCORE[fallback_tone] else fallback_tone


def recommend_follow_up_tone_with_context(
    db: Session,
    invoice: Invoice,
    fallback_tone: Tone | None = None,
) -> tuple[Tone, str, dict[str, float | int | str]]:
    today = date.today()
    delay_days = max(0, (today - invoice.due_date).days)

    history = db.scalars(
        select(Invoice)
        .where(
            Invoice.customer_email == invoice.customer_email,
            Invoice.company_id == invoice.company_id,
        )
        .order_by(Invoice.created_at.asc())
    ).all()

    total = len(history)
    late_or_overdue = 0
    for item in history:
        if item.status == InvoiceStatus.PENDING and item.due_date < today:
            late_or_overdue += 1
        elif item.status == InvoiceStatus.PAID and item.paid_at and item.paid_at.date() > item.due_date:
            late_or_overdue += 1

    late_rate = (late_or_overdue / total) if total else 0.0

    recommended = Tone.FRIENDLY
    rationale = "Friendly tone selected for low delay, low amount, and healthy payment behavior."
    if delay_days >= 10 or invoice.amount >= 5000 or late_rate >= 0.6:
        recommended = Tone.STRICT
        rationale = "Strict tone selected due to high delay, high amount, or repeatedly late payments."
    elif delay_days >= 5 or invoice.amount >= 1500 or late_rate >= 0.3:
        recommended = Tone.PROFESSIONAL
        rationale = "Professional tone selected due to moderate delay, invoice amount, or mixed payment history."

    final_tone = recommended
    if fallback_tone and _TONE_SCORE[fallback_tone] > _TONE_SCORE[recommended]:
        final_tone = fallback_tone
        rationale = (
            f"Manual baseline tone '{fallback_tone.value}' is stricter than the smart recommendation; honoring stricter tone."
        )

    factors = {
        "delay_days": delay_days,
        "invoice_amount": float(invoice.amount),
        "history_total": total,
        "history_late_or_overdue": late_or_overdue,
        "history_late_rate": round(late_rate, 4),
        "recommended_tone": recommended.value,
        "final_tone": final_tone.value,
    }
    return final_tone, rationale, factors
