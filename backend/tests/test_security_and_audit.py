from __future__ import annotations

from datetime import date, timedelta
import importlib
from io import BytesIO
import sys

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
import pyotp


APP_MODULES = [
    "app.api",
    "app.api.support",
    "app.api.routes",
    "app.api.routes.auth",
    "app.api.routes.emails",
    "app.api.routes.invoices",
    "app.main",
    "app.security",
    "app.services",
    "app.services.ai_service",
    "app.services.email_service",
    "app.services.invoice_service",
    "app.services.scheduler_service",
    "app.models",
    "app.database",
    "app.config",
]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("AUTH_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("AUTH_RATE_LIMIT_REQUESTS", "3")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")
    monkeypatch.setenv("DRY_RUN_EMAIL", "true")

    for module_name in APP_MODULES:
        sys.modules.pop(module_name, None)

    main = importlib.import_module("app.main")
    with TestClient(main.app) as test_client:
        yield test_client


def _signup(client: TestClient, username: str, email: str, password: str = "StrongPass123!"):
    response = client.post(
        "/auth/signup",
        json={"username": username, "email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    return payload["access_token"], payload["user"]


def test_payment_page_escapes_html_and_confirm_is_idempotent(client: TestClient):
    token, _ = _signup(client, "admin_user", "admin_user@example.com")
    auth = {"Authorization": f"Bearer {token}"}

    create_invoice = client.post(
        "/invoices",
        headers=auth,
        json={
            "customer_name": "<script>alert(1)</script>",
            "customer_email": "customer@example.com",
            "amount": 123.45,
            "due_date": (date.today() - timedelta(days=2)).isoformat(),
        },
    )
    assert create_invoice.status_code == 200, create_invoice.text
    invoice_payload = create_invoice.json()
    payment_token = invoice_payload["payment_url"].split("/payments/pay/", 1)[1].split("?", 1)[0]

    checkout = client.get(f"/payments/pay/{payment_token}")
    assert checkout.status_code == 200, checkout.text
    assert "<script>alert(1)</script>" not in checkout.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in checkout.text

    first = client.post(f"/payments/confirm/{payment_token}", json={"payment_reference": "REF-1"})
    second = client.post(f"/payments/confirm/{payment_token}", json={"payment_reference": "REF-2"})
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["payment_reference"] == "REF-1"
    assert second.json()["payment_reference"] == "REF-1"


def test_team_and_audit_endpoints_enforce_admin_role(client: TestClient):
    admin_token, _ = _signup(client, "admin2", "admin2@example.com")
    team_token, _ = _signup(client, "team2", "team2@example.com")

    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    team_headers = {"Authorization": f"Bearer {team_token}"}

    create_invoice = client.post(
        "/invoices",
        headers=admin_headers,
        json={
            "customer_name": "Audit Customer",
            "customer_email": "audit@example.com",
            "amount": 500,
            "due_date": date.today().isoformat(),
        },
    )
    assert create_invoice.status_code == 200, create_invoice.text
    invoice_id = create_invoice.json()["id"]

    mark_paid = client.post(
        f"/invoices/{invoice_id}/mark-paid",
        headers=admin_headers,
        json={"payment_reference": "PAID-AUDIT-1"},
    )
    assert mark_paid.status_code == 200, mark_paid.text

    team_list = client.get("/team/users", headers=team_headers)
    team_audit = client.get("/audit/logs", headers=team_headers)
    assert team_list.status_code == 403
    assert team_audit.status_code == 403

    admin_audit = client.get("/audit/logs", headers=admin_headers)
    assert admin_audit.status_code == 200, admin_audit.text
    actions = {entry["action"] for entry in admin_audit.json()}
    assert "invoice_created" in actions
    assert "invoice_marked_paid" in actions


def test_auth_rate_limit_triggers_429(client: TestClient):
    _signup(client, "admin3", "admin3@example.com")
    for _ in range(2):
        bad_login = client.post("/auth/login", json={"email": "admin3@example.com", "password": "wrong-pass"})
        assert bad_login.status_code == 401

    limited = client.post("/auth/login", json={"email": "admin3@example.com", "password": "wrong-pass"})
    assert limited.status_code == 429


def test_queue_processes_approved_email_jobs(client: TestClient):
    token, _ = _signup(client, "admin4", "admin4@example.com")
    auth = {"Authorization": f"Bearer {token}"}

    inv = client.post(
        "/invoices",
        headers=auth,
        json={
            "customer_name": "Queue Customer",
            "customer_email": "queue.customer@example.com",
            "amount": 345.67,
            "due_date": (date.today() - timedelta(days=1)).isoformat(),
        },
    )
    assert inv.status_code == 200, inv.text
    invoice_id = inv.json()["id"]

    draft = client.post(
        "/generate-email",
        headers=auth,
        json={"invoice_id": invoice_id, "tone": "professional"},
    )
    assert draft.status_code == 200, draft.text
    email_id = draft.json()["id"]

    approve = client.post(
        f"/emails/{email_id}/approve",
        headers=auth,
        json={"provider": "smtp"},
    )
    assert approve.status_code == 200, approve.text
    assert approve.json()["status"] == "approved"

    run_now = client.post("/jobs/run-now", headers=auth)
    assert run_now.status_code == 200, run_now.text
    assert run_now.json()["succeeded"] >= 1

    history = client.get("/emails", headers=auth)
    assert history.status_code == 200, history.text
    target = next(item for item in history.json() if item["id"] == email_id)
    assert target["status"] in {"delivered", "opened", "sent"}


def test_generate_email_supports_message_styles(client: TestClient):
    token, _ = _signup(client, "admin_style", "admin_style@example.com")
    auth = {"Authorization": f"Bearer {token}"}

    inv = client.post(
        "/invoices",
        headers=auth,
        json={
            "customer_name": "Styled Customer",
            "customer_email": "styled@example.com",
            "amount": 210.0,
            "due_date": (date.today() - timedelta(days=14)).isoformat(),
        },
    )
    assert inv.status_code == 200, inv.text
    invoice_id = inv.json()["id"]

    draft = client.post(
        "/generate-email",
        headers=auth,
        json={"invoice_id": invoice_id, "tone": "strict", "message_style": "urgent_payment_notice"},
    )
    assert draft.status_code == 200, draft.text
    body = draft.json()
    assert "Urgent Payment Notice" in body["subject"]
    assert "Immediate action is required" in body["body"]


def test_automation_status_and_manual_trigger(client: TestClient):
    token, _ = _signup(client, "admin_scheduler", "admin_scheduler@example.com")
    auth = {"Authorization": f"Bearer {token}"}

    status = client.get("/automation/status", headers=auth)
    assert status.status_code == 200, status.text
    assert "interval_minutes" in status.json()
    assert "running" in status.json()

    trigger = client.post("/automation/run-now", headers=auth)
    assert trigger.status_code == 200, trigger.text
    assert trigger.json()["accepted"] is True


def test_invoice_upload_accepts_excel_file(client: TestClient):
    token, _ = _signup(client, "admin_import", "admin_import@example.com")
    auth = {"Authorization": f"Bearer {token}"}

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["customer_name", "customer_email", "amount", "due_date", "customer_phone"])
    sheet.append(["Excel Customer", "excel.customer@example.com", 275.5, date.today().isoformat(), "+15550001111"])

    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)

    response = client.post(
        "/invoices/upload",
        headers=auth,
        files={"file": ("invoices.xlsx", stream.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created_count"] == 1
    assert body["error_count"] == 0
    assert body["invoices"][0]["customer_email"] == "excel.customer@example.com"


def test_payment_webhook_is_idempotent(client: TestClient):
    token, _ = _signup(client, "admin5", "admin5@example.com")
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


def test_email_status_webhook_updates_email_and_ops_metrics(client: TestClient):
    token, _ = _signup(client, "admin6", "admin6@example.com")
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
    draft = client.post("/generate-email", headers=auth, json={"invoice_id": invoice_id, "tone": "professional"})
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


def test_refresh_and_logout_token_flow(client: TestClient):
    signup = client.post(
        "/auth/signup",
        json={"username": "refresh_user", "email": "refresh_user@example.com", "password": "StrongPass123!"},
    )
    assert signup.status_code == 200, signup.text
    body = signup.json()
    access_token = body["access_token"]
    refresh_token = body["refresh_token"]
    assert refresh_token

    refreshed = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert refreshed.status_code == 200, refreshed.text
    new_access = refreshed.json()["access_token"]
    new_refresh = refreshed.json()["refresh_token"]
    assert new_access and new_refresh and new_refresh != refresh_token

    logout = client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {new_access}"},
        json={"refresh_token": new_refresh},
    )
    assert logout.status_code == 200, logout.text

    # Revoked access token should fail on protected route.
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {new_access}"})
    assert me.status_code == 401

    # Revoked refresh token should fail.
    refresh_again = client.post("/auth/refresh", json={"refresh_token": new_refresh})
    assert refresh_again.status_code == 401


def test_mfa_setup_enable_and_login_requires_otp(client: TestClient):
    signup = client.post(
        "/auth/signup",
        json={"username": "mfa_user", "email": "mfa_user@example.com", "password": "StrongPass123!"},
    )
    assert signup.status_code == 200, signup.text
    token = signup.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    setup = client.post("/auth/mfa/setup", headers=headers)
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    code = pyotp.TOTP(secret).now()

    enable = client.post("/auth/mfa/enable", headers=headers, json={"otp_code": code})
    assert enable.status_code == 200, enable.text
    assert enable.json()["mfa_enabled"] is True

    login_without_otp = client.post(
        "/auth/login",
        json={"email": "mfa_user@example.com", "password": "StrongPass123!"},
    )
    assert login_without_otp.status_code == 401

    login_with_otp = client.post(
        "/auth/login",
        json={"email": "mfa_user@example.com", "password": "StrongPass123!", "otp_code": pyotp.TOTP(secret).now()},
    )
    assert login_with_otp.status_code == 200
