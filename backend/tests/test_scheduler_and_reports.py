from __future__ import annotations

from datetime import date, timedelta

from .conftest import signup


def test_automation_status_and_manual_trigger(client):
    token, _ = signup(client, "admin_scheduler", "admin_scheduler@example.com")
    auth = {"Authorization": f"Bearer {token}"}

    status = client.get("/automation/status", headers=auth)
    assert status.status_code == 200, status.text
    assert "interval_minutes" in status.json()
    assert "running" in status.json()

    trigger = client.post("/automation/run-now", headers=auth)
    assert trigger.status_code == 200, trigger.text
    assert trigger.json()["accepted"] is True


def test_automation_uses_day1_friendly_schedule(client):
    token, _ = signup(client, "admin_schedule_tone", "admin_schedule_tone@example.com")
    auth = {"Authorization": f"Bearer {token}"}

    inv = client.post(
        "/invoices",
        headers=auth,
        json={
            "customer_name": "Schedule Tone Customer",
            "customer_email": "schedule-tone@example.com",
            "amount": 8000.0,
            "due_date": (date.today() - timedelta(days=1)).isoformat(),
        },
    )
    assert inv.status_code == 200, inv.text
    invoice_id = inv.json()["id"]

    trigger = client.post("/automation/run-now", headers=auth)
    assert trigger.status_code == 200, trigger.text
    assert trigger.json()["accepted"] is True

    emails = client.get("/emails", headers=auth)
    assert emails.status_code == 200, emails.text
    invoice_emails = [item for item in emails.json() if item["invoice_id"] == invoice_id]
    assert invoice_emails
    assert any(item["tone"] == "friendly" for item in invoice_emails)


def test_reports_overview_contains_monthly_cashflow(client):
    token, _ = signup(client, "admin_cashflow", "admin_cashflow@example.com")
    auth = {"Authorization": f"Bearer {token}"}

    inv = client.post(
        "/invoices",
        headers=auth,
        json={
            "customer_name": "Cashflow Customer",
            "customer_email": "cashflow@example.com",
            "amount": 420.0,
            "due_date": (date.today() - timedelta(days=2)).isoformat(),
        },
    )
    assert inv.status_code == 200, inv.text
    invoice_id = inv.json()["id"]

    mark_paid = client.post(
        f"/invoices/{invoice_id}/mark-paid",
        headers=auth,
        json={"payment_reference": "CF-001"},
    )
    assert mark_paid.status_code == 200, mark_paid.text

    reports = client.get("/reports/overview", headers=auth)
    assert reports.status_code == 200, reports.text
    payload = reports.json()
    assert "monthly_cashflow" in payload
    assert payload["monthly_cashflow"][0]["cash_in"] >= 0


def test_reports_overview_and_tone_rationale_fields(client):
    token, _ = signup(client, "admin_reports", "admin_reports@example.com")
    auth = {"Authorization": f"Bearer {token}"}

    inv = client.post(
        "/invoices",
        headers=auth,
        json={
            "customer_name": "Reports Customer",
            "customer_email": "reports.customer@example.com",
            "customer_phone": "+14155552671",
            "amount": 5600.0,
            "due_date": (date.today() - timedelta(days=12)).isoformat(),
        },
    )
    assert inv.status_code == 200, inv.text

    draft = client.post(
        "/generate-email",
        headers=auth,
        json={"invoice_id": inv.json()["id"], "auto_tone": True},
    )
    assert draft.status_code == 200, draft.text
    draft_body = draft.json()
    assert draft_body["tone"] in {"friendly", "professional", "strict"}
    assert draft_body["tone_rationale"]

    reports = client.get("/reports/overview", headers=auth)
    assert reports.status_code == 200, reports.text
    payload = reports.json()
    assert "monthly_recovery" in payload
    assert "monthly_recovery_rate" in payload
    assert "avg_payment_delay_days" in payload
    assert "email_open_rate" in payload
    assert "email_click_rate" in payload
    assert "top_late_payers" in payload
