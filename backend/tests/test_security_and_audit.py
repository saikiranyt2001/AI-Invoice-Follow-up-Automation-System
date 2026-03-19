from __future__ import annotations

from datetime import date, timedelta

import pyotp

from .conftest import signup


def test_payment_page_escapes_html_and_confirm_is_idempotent(client):
    token, _ = signup(client, "admin_user", "admin_user@example.com")
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


def test_team_and_audit_endpoints_enforce_admin_role(client):
    admin_token, _ = signup(client, "admin2", "admin2@example.com")
    viewer_token, _ = signup(client, "viewer2", "viewer2@example.com")

    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

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

    team_list = client.get("/team/users", headers=viewer_headers)
    team_audit = client.get("/audit/logs", headers=viewer_headers)
    assert team_list.status_code == 403
    assert team_audit.status_code == 403

    admin_audit = client.get("/audit/logs", headers=admin_headers)
    assert admin_audit.status_code == 200, admin_audit.text
    actions = {entry["action"] for entry in admin_audit.json()}
    assert "invoice_created" in actions
    assert "invoice_marked_paid" in actions


def test_auth_rate_limit_triggers_429(client):
    signup(client, "admin3", "admin3@example.com")
    for _ in range(2):
        bad_login = client.post(
            "/auth/login", json={"email": "admin3@example.com", "password": "wrong-pass"}
        )
        assert bad_login.status_code == 401

    limited = client.post(
        "/auth/login", json={"email": "admin3@example.com", "password": "wrong-pass"}
    )
    assert limited.status_code == 429


def test_refresh_and_logout_token_flow(client):
    signup_response = client.post(
        "/auth/signup",
        json={
            "username": "refresh_user",
            "email": "refresh_user@example.com",
            "password": "StrongPass123!",
        },
    )
    assert signup_response.status_code == 200, signup_response.text
    body = signup_response.json()
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

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {new_access}"})
    assert me.status_code == 401

    refresh_again = client.post("/auth/refresh", json={"refresh_token": new_refresh})
    assert refresh_again.status_code == 401


def test_mfa_setup_enable_and_login_requires_otp(client):
    signup_response = client.post(
        "/auth/signup",
        json={
            "username": "mfa_user",
            "email": "mfa_user@example.com",
            "password": "StrongPass123!",
        },
    )
    assert signup_response.status_code == 200, signup_response.text
    token = signup_response.json()["access_token"]
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
        json={
            "email": "mfa_user@example.com",
            "password": "StrongPass123!",
            "otp_code": pyotp.TOTP(secret).now(),
        },
    )
    assert login_with_otp.status_code == 200
