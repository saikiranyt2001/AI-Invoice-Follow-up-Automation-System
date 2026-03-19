from __future__ import annotations

import base64
from email.message import EmailMessage
import smtplib
import secrets

import httpx

from app.config import get_settings


def _dry_run_twilio_sid() -> str:
    # Twilio message SIDs look like "SM" + 32 hex chars.
    return f"SM{secrets.token_hex(16)}"


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


def send_with_gmail_api(
    to_email: str,
    subject: str,
    body: str,
    tracking_pixel_url: str,
) -> tuple[bool, str | None]:
    settings = get_settings()
    if settings.dry_run_email:
        return True, None
    if not settings.gmail_access_token or not (settings.gmail_from_email or settings.smtp_from):
        return False, "Gmail API token or from email is missing"

    from_email = settings.gmail_from_email or settings.smtp_from
    message = EmailMessage()
    message["From"] = from_email
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    message.add_alternative(
        (
            f"<html><body><p>{body.replace(chr(10), '<br/>')}</p>"
            f"<img src=\"{tracking_pixel_url}\" width=\"1\" height=\"1\" alt=\"\" />"
            "</body></html>"
        ),
        subtype="html",
    )

    encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers={
                    "Authorization": f"Bearer {settings.gmail_access_token}",
                    "Content-Type": "application/json",
                },
                json={"raw": encoded_message},
            )
            if response.status_code >= 400:
                return False, f"Gmail API send failed: {response.text}"
        return True, None
    except Exception as exc:
        return False, str(exc)


def send_with_sendgrid(
    to_email: str,
    subject: str,
    body: str,
    tracking_pixel_url: str,
) -> tuple[bool, str | None]:
    settings = get_settings()
    if settings.dry_run_email:
        return True, None
    if not settings.sendgrid_api_key or not (settings.sendgrid_from_email or settings.smtp_from):
        return False, "SendGrid API key or from email is missing"

    from_email = settings.sendgrid_from_email or settings.smtp_from
    html_body = f"<p>{body.replace(chr(10), '<br/>')}</p><img src=\"{tracking_pixel_url}\" width=\"1\" height=\"1\" alt=\"\" />"

    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": from_email},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": body},
            {"type": "text/html", "value": html_body},
        ],
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={
                    "Authorization": f"Bearer {settings.sendgrid_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if response.status_code >= 400:
                return False, f"SendGrid send failed: {response.text}"
        return True, None
    except Exception as exc:
        return False, str(exc)


def send_with_sms(recipient_hint: str, body: str) -> tuple[bool, str | None]:
    settings = get_settings()
    if not settings.sms_enabled:
        return False, "SMS channel is not enabled"
    if settings.sms_dry_run:
        return True, f"sid:{_dry_run_twilio_sid()}"
    if not settings.twilio_account_sid or not settings.twilio_auth_token or not settings.twilio_from_number:
        return False, "Twilio credentials are not configured"

    to_number = recipient_hint.strip()
    if not to_number:
        return False, "Missing SMS recipient"
    if not to_number.startswith("+"):
        return False, "SMS recipient must be E.164 phone number (example: +14155552671)"

    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json",
                auth=(settings.twilio_account_sid, settings.twilio_auth_token),
                data={
                    "From": settings.twilio_from_number,
                    "To": to_number,
                    "Body": body,
                },
            )
            if response.status_code >= 400:
                return False, f"Twilio send failed: {response.text}"
            payload = response.json()
            message_sid = str(payload.get("sid") or "")
            if message_sid:
                return True, f"sid:{message_sid}"
        return True, None
    except Exception as exc:
        return False, str(exc)


def send_with_whatsapp(recipient_hint: str, body: str) -> tuple[bool, str | None]:
    settings = get_settings()
    if not settings.sms_enabled:
        return False, "WhatsApp channel is not enabled"
    if settings.sms_dry_run:
        return True, f"sid:{_dry_run_twilio_sid()}"
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        return False, "Twilio credentials are not configured"

    from_number = settings.twilio_whatsapp_from_number or settings.twilio_from_number
    if not from_number:
        return False, "Twilio WhatsApp sender is not configured"

    to_number = recipient_hint.strip()
    if not to_number:
        return False, "Missing WhatsApp recipient"
    if not to_number.startswith("+"):
        return False, "WhatsApp recipient must be E.164 phone number (example: +14155552671)"

    twilio_to = f"whatsapp:{to_number}"
    twilio_from = from_number if from_number.startswith("whatsapp:") else f"whatsapp:{from_number}"

    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json",
                auth=(settings.twilio_account_sid, settings.twilio_auth_token),
                data={
                    "From": twilio_from,
                    "To": twilio_to,
                    "Body": body,
                },
            )
            if response.status_code >= 400:
                return False, f"Twilio WhatsApp send failed: {response.text}"
            payload = response.json()
            message_sid = str(payload.get("sid") or "")
            if message_sid:
                return True, f"sid:{message_sid}"
        return True, None
    except Exception as exc:
        return False, str(exc)


def send_reminder_via_provider(
    *,
    provider: str,
    to_email: str,
    recipient_hint: str,
    subject: str,
    body: str,
    tracking_pixel_url: str,
) -> tuple[bool, str | None, str]:
    if provider == "gmail_api":
        success, error = send_with_gmail_api(to_email, subject, body, tracking_pixel_url)
        return success, error, "email"
    if provider == "sendgrid":
        success, error = send_with_sendgrid(to_email, subject, body, tracking_pixel_url)
        return success, error, "email"
    if provider == "twilio_sms":
        success, error = send_with_sms(recipient_hint, body)
        return success, error, "sms"
    if provider == "twilio_whatsapp":
        success, error = send_with_whatsapp(recipient_hint, body)
        return success, error, "whatsapp"

    success, error = send_with_smtp(to_email, subject, body, tracking_pixel_url)
    return success, error, "email"
