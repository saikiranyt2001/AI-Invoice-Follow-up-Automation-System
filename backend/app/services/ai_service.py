from __future__ import annotations

from app.email.templates import generate_email_content_with_ai
from app.models import Invoice, Tone


def generate_reminder_content(
    invoice: Invoice,
    tone: Tone,
    payment_link: str,
    message_style: str | None = None,
) -> tuple[str, str]:
    return generate_email_content_with_ai(invoice, tone, payment_link, message_style)
