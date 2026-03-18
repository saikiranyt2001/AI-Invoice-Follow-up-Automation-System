from __future__ import annotations

import json
from enum import Enum

import httpx

from app.config import get_settings
from app.models import Invoice, Tone


# Default follow-up plan: Day 3, Day 7, Day 14.
AUTOMATION_CADENCE: list[tuple[int, Tone]] = [
    (3, Tone.FRIENDLY),
    (7, Tone.PROFESSIONAL),
    (14, Tone.STRICT),
]


class MessageStyle(str, Enum):
    FRIENDLY_REMINDER = "friendly_reminder"
    PAYMENT_REMINDER = "payment_reminder"
    URGENT_PAYMENT_NOTICE = "urgent_payment_notice"


STYLE_GUIDANCE: dict[MessageStyle, dict[str, str]] = {
    MessageStyle.FRIENDLY_REMINDER: {
        "label": "Friendly reminder",
        "subject_prefix": "Friendly Reminder",
        "instruction": "Use a warm, polite tone that assumes good intent and encourages prompt payment.",
    },
    MessageStyle.PAYMENT_REMINDER: {
        "label": "Payment reminder",
        "subject_prefix": "Payment Reminder",
        "instruction": "Use a neutral professional tone focused on clarity, due date, and payment instructions.",
    },
    MessageStyle.URGENT_PAYMENT_NOTICE: {
        "label": "Urgent payment notice",
        "subject_prefix": "Urgent Payment Notice",
        "instruction": "Use a firm but professional tone that stresses the invoice is overdue and needs immediate action.",
    },
}


def _resolve_style(message_style: str | MessageStyle | None) -> MessageStyle:
    if isinstance(message_style, MessageStyle):
        return message_style
    if isinstance(message_style, str):
        normalized = message_style.strip().lower()
        for candidate in MessageStyle:
            if candidate.value == normalized:
                return candidate
    return MessageStyle.PAYMENT_REMINDER


def generate_email_content(
    invoice: Invoice,
    tone: Tone,
    payment_link: str,
    message_style: str | MessageStyle | None = None,
) -> tuple[str, str]:
    style = _resolve_style(message_style)
    subject_prefix = STYLE_GUIDANCE[style]["subject_prefix"]
    subject = f"{subject_prefix}: Invoice #{invoice.id} - ${invoice.amount:,.2f}"

    if style == MessageStyle.URGENT_PAYMENT_NOTICE or tone == Tone.STRICT:
        body = (
            f"Dear {invoice.customer_name},\n\n"
            f"This is an urgent notice that invoice #{invoice.id} for ${invoice.amount:,.2f}, due on {invoice.due_date}, remains unpaid.\n\n"
            f"Payment link: {payment_link}\n\n"
            "Immediate action is required. Please settle the outstanding amount without further delay.\n\n"
            "If payment has already been made, provide confirmation so we can update our records."
        )
    elif style == MessageStyle.FRIENDLY_REMINDER or tone == Tone.FRIENDLY:
        body = (
            f"Hi {invoice.customer_name},\n\n"
            f"I hope you are doing well. This is a friendly reminder that invoice #{invoice.id} for ${invoice.amount:,.2f} "
            f"was due on {invoice.due_date}.\n\n"
            f"You can complete payment securely here: {payment_link}\n\n"
            "If you have already made the payment, please ignore this message. "
            "Otherwise, we would appreciate it if you could process it at your earliest convenience.\n\n"
            "Thanks so much!"
        )
    else:
        body = (
            f"Dear {invoice.customer_name},\n\n"
            f"This is a payment reminder regarding invoice #{invoice.id} for ${invoice.amount:,.2f}, "
            f"which was due on {invoice.due_date}.\n\n"
            f"You can pay online using this link: {payment_link}\n\n"
            "Please arrange payment at your earliest convenience. "
            "If you have already completed the payment, kindly disregard this reminder.\n\n"
            "Best regards,\nAccounts Team"
        )

    return subject, body


def generate_email_content_with_ai(
    invoice: Invoice,
    tone: Tone,
    payment_link: str,
    message_style: str | MessageStyle | None = None,
) -> tuple[str, str]:
    settings = get_settings()
    style = _resolve_style(message_style)
    if not settings.openai_message_generation_enabled or not settings.openai_api_key:
        return generate_email_content(invoice, tone, payment_link, style)

    system_instructions = (
        "You write concise accounts receivable follow-up emails. "
        "Return only valid JSON matching the provided schema. "
        "No markdown, no code fences, no commentary."
    )

    payload = {
        "model": settings.openai_model,
        "instructions": system_instructions,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            f"Customer name: {invoice.customer_name}\n"
                            f"Invoice ID: {invoice.id}\n"
                            f"Amount due: ${invoice.amount:,.2f}\n"
                            f"Due date: {invoice.due_date}\n"
                            f"Payment link: {payment_link}\n"
                            f"Tone: {tone.value}\n"
                            f"Message style: {STYLE_GUIDANCE[style]['label']}\n"
                            f"Style instruction: {STYLE_GUIDANCE[style]['instruction']}\n"
                            "Requirements:\n"
                            "- Mention the invoice ID, amount, due date, and payment link.\n"
                            "- Keep the email under 170 words.\n"
                            "- Keep the subject under 12 words.\n"
                            "- End with a short call to action.\n"
                            "- If the customer may have already paid, mention that briefly."
                        ),
                    }
                ],
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "invoice_follow_up_email",
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "subject": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["subject", "body"],
                },
                "strict": True,
            }
        },
    }

    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                f"{settings.openai_base_url.rstrip('/')}/responses",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            content = data.get("output_text", "")
            if not content:
                for item in data.get("output", []):
                    if item.get("type") != "message":
                        continue
                    for part in item.get("content", []):
                        if part.get("type") == "output_text" and part.get("text"):
                            content = part["text"]
                            break
                    if content:
                        break

            if not content:
                return generate_email_content(invoice, tone, payment_link, style)

            parsed = json.loads(content)
            subject = str(parsed["subject"]).strip()
            body = str(parsed["body"]).strip()

            if not subject or not body:
                return generate_email_content(invoice, tone, payment_link, style)

            if "http" not in body.lower():
                body = f"{body}\n\nPay here: {payment_link}"

            return subject, body
    except Exception:
        return generate_email_content(invoice, tone, payment_link, style)
