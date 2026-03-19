from __future__ import annotations

from datetime import date, timedelta

from .conftest import signup


def test_role_based_access_admin_accountant_viewer(client):
    admin_token, _ = signup(client, "admin_rbac", "admin_rbac@example.com")
    viewer_token, _ = signup(client, "viewer_rbac", "viewer_rbac@example.com")

    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

    accountant_user = client.post(
        "/team/users",
        headers=admin_headers,
        json={
            "username": "accountant_rbac",
            "email": "accountant_rbac@example.com",
            "password": "StrongPass123!",
            "role": "accountant",
        },
    )
    assert accountant_user.status_code == 200, accountant_user.text

    accountant_login = client.post(
        "/auth/login",
        json={"email": "accountant_rbac@example.com", "password": "StrongPass123!"},
    )
    assert accountant_login.status_code == 200, accountant_login.text
    accountant_headers = {"Authorization": f"Bearer {accountant_login.json()['access_token']}"}

    create_by_accountant = client.post(
        "/invoices",
        headers=accountant_headers,
        json={
            "customer_name": "RBAC Accountant Customer",
            "customer_email": "rbac.acc@example.com",
            "amount": 250.0,
            "due_date": date.today().isoformat(),
        },
    )
    assert create_by_accountant.status_code == 200, create_by_accountant.text

    create_by_viewer = client.post(
        "/invoices",
        headers=viewer_headers,
        json={
            "customer_name": "RBAC Viewer Customer",
            "customer_email": "rbac.viewer@example.com",
            "amount": 120.0,
            "due_date": date.today().isoformat(),
        },
    )
    assert create_by_viewer.status_code == 403

    read_by_viewer = client.get("/invoices", headers=viewer_headers)
    assert read_by_viewer.status_code == 200, read_by_viewer.text


def test_queue_processes_approved_email_jobs(client):
    token, _ = signup(client, "admin4", "admin4@example.com")
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


def test_generate_email_supports_message_styles(client):
    token, _ = signup(client, "admin_style", "admin_style@example.com")
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
