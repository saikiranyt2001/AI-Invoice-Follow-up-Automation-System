from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.models import EmailStatus, Invoice, InvoiceStatus, ReminderEmail


@dataclass(slots=True)
class EmailAnalyticsSnapshot:
    total_messages: int
    sent_messages: int
    delivered_messages: int
    opened_messages: int
    clicked_messages: int
    bounced_messages: int
    spam_reported_messages: int
    failed_messages: int
    open_rate: float
    click_rate: float
    bounce_rate: float
    spam_rate: float

    def model_dump(self) -> dict[str, int | float]:
        return {
            "total_messages": self.total_messages,
            "sent_messages": self.sent_messages,
            "delivered_messages": self.delivered_messages,
            "opened_messages": self.opened_messages,
            "clicked_messages": self.clicked_messages,
            "bounced_messages": self.bounced_messages,
            "spam_reported_messages": self.spam_reported_messages,
            "failed_messages": self.failed_messages,
            "open_rate": self.open_rate,
            "click_rate": self.click_rate,
            "bounce_rate": self.bounce_rate,
            "spam_rate": self.spam_rate,
        }


def compute_email_analytics(reminders: list[ReminderEmail]) -> EmailAnalyticsSnapshot:
    total_messages = len(reminders)
    sent_messages = sum(
        1
        for item in reminders
        if item.sent_at is not None
        or item.status
        in {EmailStatus.SENT, EmailStatus.DELIVERED, EmailStatus.OPENED, EmailStatus.FAILED}
    )
    delivered_messages = sum(
        1
        for item in reminders
        if item.delivered_at is not None
        or item.status in {EmailStatus.DELIVERED, EmailStatus.OPENED}
    )
    opened_messages = sum(
        1 for item in reminders if item.opened_at is not None or item.status == EmailStatus.OPENED
    )
    clicked_messages = sum(1 for item in reminders if int(item.click_count or 0) > 0)
    bounced_messages = sum(1 for item in reminders if item.bounced_at is not None)
    spam_reported_messages = sum(1 for item in reminders if item.spam_reported_at is not None)
    failed_messages = sum(1 for item in reminders if item.status == EmailStatus.FAILED)

    denominator = max(1, sent_messages)
    return EmailAnalyticsSnapshot(
        total_messages=total_messages,
        sent_messages=sent_messages,
        delivered_messages=delivered_messages,
        opened_messages=opened_messages,
        clicked_messages=clicked_messages,
        bounced_messages=bounced_messages,
        spam_reported_messages=spam_reported_messages,
        failed_messages=failed_messages,
        open_rate=round((opened_messages / denominator) * 100, 1),
        click_rate=round((clicked_messages / denominator) * 100, 1),
        bounce_rate=round((bounced_messages / denominator) * 100, 1),
        spam_rate=round((spam_reported_messages / denominator) * 100, 1),
    )


def build_reports_overview(
    invoices: list[Invoice],
    reminders: list[ReminderEmail],
    *,
    top_late_payers: list[dict[str, object]],
) -> dict[str, object]:
    if not invoices:
        return {
            "monthly_recovery": [],
            "monthly_cashflow": [],
            "monthly_recovery_rate": 0.0,
            "avg_payment_delay_days": 0.0,
            "email_open_rate": 0.0,
            "email_click_rate": 0.0,
            "top_late_payers": top_late_payers,
        }

    monthly_agg: dict[str, dict[str, float]] = {}
    paid_delay_days: list[int] = []

    for item in invoices:
        month = _month_key(item.due_date)
        bucket = monthly_agg.setdefault(month, {"invoiced": 0.0, "paid": 0.0})
        bucket["invoiced"] += float(item.amount)
        if item.status == InvoiceStatus.PAID:
            bucket["paid"] += float(item.amount)
            if item.paid_at:
                paid_delay_days.append(max(0, (item.paid_at.date() - item.due_date).days))

    month_keys = sorted(monthly_agg.keys())[-6:]
    monthly_recovery: list[dict[str, object]] = []
    monthly_cashflow: list[dict[str, object]] = []
    total_invoiced = 0.0
    total_paid = 0.0

    for month in month_keys:
        bucket = monthly_agg[month]
        invoiced_amount = round(bucket["invoiced"], 2)
        paid_amount = round(bucket["paid"], 2)
        rate = round((paid_amount / invoiced_amount) * 100, 1) if invoiced_amount > 0 else 0.0
        outstanding_amount = round(max(0.0, invoiced_amount - paid_amount), 2)

        monthly_recovery.append(
            {
                "month": _month_label(month),
                "invoiced_amount": invoiced_amount,
                "paid_amount": paid_amount,
                "recovery_rate": rate,
            }
        )
        monthly_cashflow.append(
            {
                "month": _month_label(month),
                "cash_in": paid_amount,
                "cash_outstanding": outstanding_amount,
                "net_cashflow": round(paid_amount - outstanding_amount, 2),
            }
        )
        total_invoiced += invoiced_amount
        total_paid += paid_amount

    email_metrics = compute_email_analytics(reminders)
    return {
        "monthly_recovery": monthly_recovery,
        "monthly_cashflow": monthly_cashflow,
        "monthly_recovery_rate": round((total_paid / total_invoiced) * 100, 1)
        if total_invoiced > 0
        else 0.0,
        "avg_payment_delay_days": round(sum(paid_delay_days) / len(paid_delay_days), 1)
        if paid_delay_days
        else 0.0,
        "email_open_rate": email_metrics.open_rate,
        "email_click_rate": email_metrics.click_rate,
        "top_late_payers": top_late_payers,
    }


def _month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def _month_label(month_key: str) -> str:
    year, month = month_key.split("-")
    month_start = date(int(year), int(month), 1)
    return month_start.strftime("%b %Y")
