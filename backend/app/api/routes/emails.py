from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.support import enqueue_job, get_active_company, record_audit_event
from app.database import get_db
from app.models import EmailStatus, Invoice, InvoiceStatus, ReminderEmail, User
from app.schemas import EmailGenerateRequest, ReminderEmailOut, ReminderEmailUpdate, SendEmailRequest
from app.security import get_current_user
from app.services.email_service import create_pending_reminder

router = APIRouter(tags=["emails"])


@router.post("/generate-email", response_model=ReminderEmailOut)
def generate_email(
    payload: EmailGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    active_company = get_active_company(db, current_user)
    invoice = db.get(Invoice, payload.invoice_id)
    if not invoice or invoice.company_id != active_company.id:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status == InvoiceStatus.PAID:
        raise HTTPException(status_code=400, detail="Cannot generate reminder for a paid invoice")

    reminder = create_pending_reminder(
        db,
        invoice,
        payload.tone,
        current_user.id,
        active_company.id,
        payload.message_style.value,
    )
    record_audit_event(
        db,
        action="reminder_generated",
        entity_type="reminder_email",
        entity_id=reminder.id,
        user_id=current_user.id,
        company_id=active_company.id,
        details={"invoice_id": invoice.id, "tone": payload.tone.value, "message_style": payload.message_style.value},
    )
    return reminder


@router.get("/emails/pending-approvals", response_model=list[ReminderEmailOut])
def pending_approvals(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    active_company = get_active_company(db, current_user)
    return db.scalars(
        select(ReminderEmail)
        .where(
            ReminderEmail.status == EmailStatus.PENDING_APPROVAL,
            ReminderEmail.company_id == active_company.id,
        )
        .order_by(ReminderEmail.created_at.desc())
    ).all()


@router.get("/emails", response_model=list[ReminderEmailOut])
def list_emails(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    active_company = get_active_company(db, current_user)
    return db.scalars(
        select(ReminderEmail)
        .where(ReminderEmail.company_id == active_company.id)
        .order_by(ReminderEmail.created_at.desc())
    ).all()


@router.patch("/emails/{email_id}/edit", response_model=ReminderEmailOut)
def edit_email(
    email_id: int,
    payload: ReminderEmailUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    active_company = get_active_company(db, current_user)
    reminder = db.get(ReminderEmail, email_id)
    if not reminder or reminder.company_id != active_company.id:
        raise HTTPException(status_code=404, detail="Email not found")
    if reminder.status != EmailStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=400, detail="Only pending approval emails can be edited")
    reminder.subject = payload.subject
    reminder.body = payload.body
    db.commit()
    db.refresh(reminder)
    return reminder


@router.post("/emails/{email_id}/approve", response_model=ReminderEmailOut)
def approve_email(
    email_id: int,
    payload: SendEmailRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    active_company = get_active_company(db, current_user)
    reminder = db.get(ReminderEmail, email_id)
    if not reminder or reminder.company_id != active_company.id:
        raise HTTPException(status_code=404, detail="Email not found")
    if reminder.status != EmailStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=400, detail="Email is not pending approval")

    reminder.status = EmailStatus.APPROVED
    db.commit()
    db.refresh(reminder)
    job = enqueue_job(
        db,
        job_type="send_reminder_email",
        payload={"reminder_id": reminder.id, "provider": payload.provider},
        company_id=active_company.id,
        user_id=current_user.id,
        max_attempts=3,
    )
    record_audit_event(
        db,
        action="reminder_approved_and_queued",
        entity_type="reminder_email",
        entity_id=reminder.id,
        user_id=current_user.id,
        company_id=active_company.id,
        details={"provider": payload.provider, "queue_job_id": job.id},
    )
    return reminder


@router.post("/emails/{email_id}/send", response_model=ReminderEmailOut)
def send_email_direct(
    email_id: int,
    payload: SendEmailRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    active_company = get_active_company(db, current_user)
    reminder = db.get(ReminderEmail, email_id)
    if not reminder or reminder.company_id != active_company.id:
        raise HTTPException(status_code=404, detail="Email not found")
    if reminder.status not in {EmailStatus.PENDING_APPROVAL, EmailStatus.APPROVED, EmailStatus.FAILED}:
        raise HTTPException(status_code=400, detail="Email cannot be sent in current state")
    if reminder.status == EmailStatus.PENDING_APPROVAL:
        reminder.status = EmailStatus.APPROVED
        db.commit()
        db.refresh(reminder)

    job = enqueue_job(
        db,
        job_type="send_reminder_email",
        payload={"reminder_id": reminder.id, "provider": payload.provider},
        company_id=active_company.id,
        user_id=current_user.id,
        max_attempts=3,
    )
    record_audit_event(
        db,
        action="reminder_send_queued",
        entity_type="reminder_email",
        entity_id=reminder.id,
        user_id=current_user.id,
        company_id=active_company.id,
        details={"provider": payload.provider, "queue_job_id": job.id},
    )
    return reminder


@router.post("/emails/{email_id}/reject", response_model=ReminderEmailOut)
def reject_email(email_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    active_company = get_active_company(db, current_user)
    reminder = db.get(ReminderEmail, email_id)
    if not reminder or reminder.company_id != active_company.id:
        raise HTTPException(status_code=404, detail="Email not found")
    if reminder.status != EmailStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=400, detail="Email is not pending approval")
    reminder.status = EmailStatus.REJECTED
    db.commit()
    db.refresh(reminder)
    record_audit_event(
        db,
        action="reminder_rejected",
        entity_type="reminder_email",
        entity_id=reminder.id,
        user_id=current_user.id,
        company_id=active_company.id,
    )
    return reminder
