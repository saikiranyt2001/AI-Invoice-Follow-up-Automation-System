from __future__ import annotations

from datetime import date, timedelta
from time import sleep

from .conftest import signup


def test_payment_webhook_is_idempotent(client):
    token, _ = signup(client, "admin5", "admin5@example.com")
    auth = {"Authorization": f"Bearer {token}"}
    inv = client.post(
        "/invoices",
        headers=auth,
        json={
            "customer_name": "Webhook Pay Customer",
            "customer_email": "wp@example.com",
            "amount": 99.99,
            "due_date": date.today().isoformat(),
        },
    )
    assert inv.status_code == 200, inv.text
    invoice_id = inv.json()["id"]

    payload = {
        "invoice_id": invoice_id,
        "payment_reference": "WEBHOOK-REF-1",
        "idempotency_key": "pay-event-001",
        "source": "stripe",
    }
    first = client.post("/webhooks/payments/confirm", json=payload)
    second = client.post("/webhooks/payments/confirm", json=payload)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True

    invoices = client.get("/invoices", headers=auth)
    assert invoices.status_code == 200
    item = next(row for row in invoices.json() if row["id"] == invoice_id)
    assert item["status"] == "paid"
    assert item["payment_reference"] == "WEBHOOK-REF-1"


def test_email_status_webhook_updates_email_and_ops_metrics(client):
    token, _ = signup(client, "admin6", "admin6@example.com")
    auth = {"Authorization": f"Bearer {token}"}
    inv = client.post(
        "/invoices",
        headers=auth,
        json={
            "customer_name": "Webhook Email Customer",
            "customer_email": "we@example.com",
            "amount": 120.0,
            "due_date": (date.today() - timedelta(days=1)).isoformat(),
        },
    )
    assert inv.status_code == 200, inv.text
    invoice_id = inv.json()["id"]
    draft = client.post(
        "/generate-email", headers=auth, json={"invoice_id": invoice_id, "tone": "professional"}
    )
    assert draft.status_code == 200, draft.text
    email_id = draft.json()["id"]
    approve = client.post(f"/emails/{email_id}/approve", headers=auth, json={"provider": "smtp"})
    assert approve.status_code == 200, approve.text
    client.post("/jobs/run-now", headers=auth)

    emails = client.get("/emails", headers=auth)
    sent_item = next(item for item in emails.json() if item["id"] == email_id)
    provider_message_id = sent_item["provider_message_id"]
    assert provider_message_id

    webhook = client.post(
        "/webhooks/email/status",
        json={
            "idempotency_key": "email-event-001",
            "provider_message_id": provider_message_id,
            "status": "opened",
            "source": "sendgrid",
        },
    )
    assert webhook.status_code == 200, webhook.text
    assert webhook.json()["duplicate"] is False

    dup = client.post(
        "/webhooks/email/status",
        json={
            "idempotency_key": "email-event-001",
            "provider_message_id": provider_message_id,
            "status": "opened",
            "source": "sendgrid",
        },
    )
    assert dup.status_code == 200
    assert dup.json()["duplicate"] is True

    emails_after = client.get("/emails", headers=auth)
    updated = next(item for item in emails_after.json() if item["id"] == email_id)
    assert updated["status"] == "opened"

    metrics = client.get("/ops/metrics", headers=auth)
    assert metrics.status_code == 200, metrics.text
    body = metrics.json()
    assert body["total_invoices"] >= 1
    assert body["webhook_events_24h"] >= 1


def test_email_analytics_tracks_click_bounce_and_spam(client):
    token, _ = signup(client, "admin_email_analytics", "admin_email_analytics@example.com")
    auth = {"Authorization": f"Bearer {token}"}

    inv = client.post(
        "/invoices",
        headers=auth,
        json={
            "customer_name": "Email Analytics Customer",
            "customer_email": "ea@example.com",
            "amount": 199.0,
            "due_date": (date.today() - timedelta(days=1)).isoformat(),
        },
    )
    assert inv.status_code == 200, inv.text
    invoice_id = inv.json()["id"]

    draft = client.post(
        "/generate-email", headers=auth, json={"invoice_id": invoice_id, "tone": "professional"}
    )
    assert draft.status_code == 200, draft.text
    email_id = draft.json()["id"]

    approve = client.post(f"/emails/{email_id}/approve", headers=auth, json={"provider": "smtp"})
    assert approve.status_code == 200, approve.text
    client.post("/jobs/run-now", headers=auth)

    emails = client.get("/emails", headers=auth)
    item = next(row for row in emails.json() if row["id"] == email_id)
    token_value = item.get("tracking_token")
    provider_message_id = item.get("provider_message_id")
    assert token_value
    assert provider_message_id

    click = client.get(f"/emails/track/click/{token_value}", follow_redirects=False)
    assert click.status_code in {200, 302}

    bounce = client.post(
        "/webhooks/email/status",
        json={
            "idempotency_key": "email-bounce-001",
            "provider_message_id": provider_message_id,
            "status": "bounced",
            "source": "sendgrid",
        },
    )
    assert bounce.status_code == 200, bounce.text

    spam = client.post(
        "/webhooks/email/status",
        json={
            "idempotency_key": "email-spam-001",
            "provider_message_id": provider_message_id,
            "status": "spam",
            "source": "sendgrid",
        },
    )
    assert spam.status_code == 200, spam.text

    analytics = client.get("/emails/analytics", headers=auth)
    assert analytics.status_code == 200, analytics.text
    body = analytics.json()
    assert body["clicked_messages"] >= 1
    assert body["bounced_messages"] >= 1
    assert body["spam_reported_messages"] >= 1


def test_twilio_webhook_simulator_updates_latest_whatsapp_reminder(client):
    token, _ = signup(client, "admin_twilio", "admin_twilio@example.com")
    auth = {"Authorization": f"Bearer {token}"}

    inv = client.post(
        "/invoices",
        headers=auth,
        json={
            "customer_name": "Twilio Customer",
            "customer_email": "twilio.customer@example.com",
            "customer_phone": "+14155552671",
            "amount": 1800.0,
            "due_date": (date.today() - timedelta(days=7)).isoformat(),
        },
    )
    assert inv.status_code == 200, inv.text

    draft = client.post(
        "/generate-email",
        headers=auth,
        json={"invoice_id": inv.json()["id"], "auto_tone": True},
    )
    assert draft.status_code == 200, draft.text
    email_id = draft.json()["id"]

    send_now = client.post(
        f"/emails/{email_id}/send", headers=auth, json={"provider": "twilio_whatsapp"}
    )
    assert send_now.status_code == 200, send_now.text

    provider_sid = None
    for _ in range(3):
        run_now = client.post("/jobs/run-now", headers=auth)
        assert run_now.status_code == 200, run_now.text

        emails_before = client.get("/emails", headers=auth)
        assert emails_before.status_code == 200, emails_before.text
        before = next(item for item in emails_before.json() if item["id"] == email_id)
        provider_sid = before.get("provider_message_id")
        if provider_sid:
            break
        sleep(0.05)

    assert provider_sid and provider_sid.startswith("SM")

    webhook = client.post(
        "/webhooks/twilio/status",
        json={
            "MessageSid": provider_sid,
            "MessageStatus": "read",
            "To": "+14155552671",
            "From": "whatsapp:+14155238886",
        },
    )
    assert webhook.status_code == 200, webhook.text
    assert webhook.json()["accepted"] is True

    emails = client.get("/emails", headers=auth)
    assert emails.status_code == 200, emails.text
    updated = next(item for item in emails.json() if item["id"] == email_id)
    assert updated["status"] == "opened"
