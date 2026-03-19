from __future__ import annotations

from datetime import datetime, timedelta
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Company, CompanyMembership, Invoice, JobQueue, RefreshToken, ReminderEmail, User
from app.schemas import InvoiceOut, TokenOut
from app.security import create_access_token, hash_refresh_token, refresh_token_raw
from app.services.invoice_service import build_payment_link, ensure_payment_token, is_overdue
from app.time_utils import utcnow


def issue_auth_tokens(db: Session, user: User, refresh_token_days: int) -> TokenOut:
    access_token = create_access_token(user.email)
    refresh_raw = refresh_token_raw()
    expires_at = utcnow() + timedelta(days=max(1, refresh_token_days))
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(refresh_raw),
            expires_at=expires_at,
            revoked=0,
        )
    )
    db.commit()
    return TokenOut(access_token=access_token, refresh_token=refresh_raw, user=user)


def record_audit_event(
    db: Session,
    *,
    action: str,
    entity_type: str,
    user_id: int | None,
    company_id: int | None,
    entity_id: int | None = None,
    details: dict[str, object] | None = None,
) -> None:
    event = AuditLog(
        action=action,
        entity_type=entity_type,
        user_id=user_id,
        company_id=company_id,
        entity_id=entity_id,
        details_json=json.dumps(details or {}),
    )
    db.add(event)
    db.commit()


def invoice_to_out(invoice: Invoice, db: Session) -> InvoiceOut:
    ensure_payment_token(db, invoice)
    return InvoiceOut(
        id=invoice.id,
        customer_name=invoice.customer_name,
        customer_email=invoice.customer_email,
        customer_phone=invoice.customer_phone,
        amount=invoice.amount,
        due_date=invoice.due_date,
        status=invoice.status,
        is_overdue=is_overdue(invoice),
        payment_url=build_payment_link(invoice),
        payment_reference=invoice.payment_reference,
        paid_at=invoice.paid_at,
    )


def enqueue_job(
    db: Session,
    *,
    job_type: str,
    payload: dict[str, object],
    company_id: int | None,
    user_id: int | None,
    available_at: datetime | None = None,
    max_attempts: int = 3,
) -> JobQueue:
    job = JobQueue(
        company_id=company_id,
        user_id=user_id,
        job_type=job_type,
        payload_json=json.dumps(payload),
        status="queued",
        attempts=0,
        max_attempts=max(1, max_attempts),
        available_at=available_at or utcnow(),
        updated_at=utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _default_company_name(user: User) -> str:
    return f"{user.username} Company"


def _company_accessible(db: Session, user: User, company_id: int) -> bool:
    owns = db.scalar(select(Company.id).where(Company.id == company_id, Company.owner_user_id == user.id))
    if owns:
        return True
    member = db.scalar(
        select(CompanyMembership.id).where(
            CompanyMembership.company_id == company_id,
            CompanyMembership.user_id == user.id,
        )
    )
    return bool(member)


def _get_accessible_companies(db: Session, user: User) -> list[Company]:
    owned_ids = db.scalars(select(Company.id).where(Company.owner_user_id == user.id)).all()
    member_ids = db.scalars(select(CompanyMembership.company_id).where(CompanyMembership.user_id == user.id)).all()
    ids = sorted(set([*owned_ids, *member_ids]))
    if not ids:
        return []
    return db.scalars(select(Company).where(Company.id.in_(ids)).order_by(Company.created_at.asc(), Company.id.asc())).all()


def get_active_company(db: Session, user: User) -> Company:
    active: Company | None = None
    if user.active_company_id and _company_accessible(db, user, user.active_company_id):
        active = db.scalar(select(Company).where(Company.id == user.active_company_id))
    if not active:
        accessible = _get_accessible_companies(db, user)
        active = accessible[0] if accessible else None
    if not active:
        active = Company(owner_user_id=user.id, name=_default_company_name(user))
        db.add(active)
        db.flush()
        db.add(CompanyMembership(company_id=active.id, user_id=user.id))
    if user.active_company_id != active.id:
        user.active_company_id = active.id

    db.flush()
    db.query(Invoice).filter(Invoice.user_id == user.id, Invoice.company_id.is_(None)).update(
        {Invoice.company_id: active.id},
        synchronize_session=False,
    )
    db.query(ReminderEmail).filter(ReminderEmail.user_id == user.id, ReminderEmail.company_id.is_(None)).update(
        {ReminderEmail.company_id: active.id},
        synchronize_session=False,
    )
    db.commit()
    db.refresh(user)
    db.refresh(active)
    return active
