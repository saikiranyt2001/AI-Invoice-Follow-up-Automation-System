from __future__ import annotations

from datetime import date, timedelta

from app.models import EmailStatus, Invoice, InvoiceStatus, ReminderEmail
from app.services.analytics_service import build_reports_overview, compute_email_analytics
from app.time_utils import utcnow


def test_compute_email_analytics_and_reports_use_consistent_rates():
    due_date = date.today() - timedelta(days=10)
    paid_at = utcnow()
    invoice = Invoice(
        customer_name="Analytics Customer",
        customer_email="analytics@example.com",
        amount=100.0,
        due_date=due_date,
        status=InvoiceStatus.PAID,
        paid_at=paid_at,
    )
    reminder = ReminderEmail(
        invoice_id=1,
        subject="Reminder",
        body="Body",
        status=EmailStatus.OPENED,
        sent_at=utcnow(),
        delivered_at=utcnow(),
        opened_at=utcnow(),
        click_count=1,
    )

    analytics = compute_email_analytics([reminder])
    overview = build_reports_overview([invoice], [reminder], top_late_payers=[])

    assert analytics.open_rate == 100.0
    assert analytics.click_rate == 100.0
    assert overview["email_open_rate"] == analytics.open_rate
    assert overview["email_click_rate"] == analytics.click_rate
    assert overview["monthly_recovery_rate"] == 100.0
