from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.support import get_active_company, invoice_to_out, record_audit_event
from app.database import get_db
from app.invoice_import import parse_invoice_file, validate_invoice_rows
from app.models import Invoice, InvoiceStatus, User
from app.schemas import InvoiceCreate, InvoiceImportOut, InvoiceOut, InvoiceStatusUpdate, PaymentConfirmRequest
from app.security import get_current_user
from app.services.invoice_service import is_overdue, mark_invoice_paid
from app.services.invoice_service import build_payment_link
from app.services.invoice_pdf_service import build_invoice_pdf

router = APIRouter(tags=["invoices"])


@router.post("/invoices", response_model=InvoiceOut)
def create_invoice(
    payload: InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    active_company = get_active_company(db, current_user)
    invoice = Invoice(**payload.model_dump(), user_id=current_user.id, company_id=active_company.id)
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    record_audit_event(
        db,
        action="invoice_created",
        entity_type="invoice",
        entity_id=invoice.id,
        user_id=current_user.id,
        company_id=active_company.id,
        details={"amount": invoice.amount, "due_date": invoice.due_date.isoformat()},
    )
    return invoice_to_out(invoice, db)


@router.post("/invoices/upload", response_model=InvoiceImportOut)
def upload_invoices(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    active_company = get_active_company(db, current_user)
    if not file.filename:
        raise HTTPException(status_code=400, detail="Please choose a CSV or Excel file")
    try:
        rows = parse_invoice_file(file.filename, file.file.read())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    validation_errors = validate_invoice_rows(rows)
    if validation_errors:
        raise HTTPException(status_code=400, detail="; ".join(validation_errors[:8]))

    created: list[InvoiceOut] = []
    for row in rows:
        invoice = Invoice(
            user_id=current_user.id,
            company_id=active_company.id,
            customer_name=row["customer_name"],
            customer_email=row["customer_email"],
            customer_phone=row.get("customer_phone") or None,
            amount=float(row["amount"]),
            due_date=date.fromisoformat(row["due_date"]),
        )
        db.add(invoice)
        db.flush()
        created.append(invoice_to_out(invoice, db))
        record_audit_event(
            db,
            action="invoice_created",
            entity_type="invoice",
            entity_id=invoice.id,
            user_id=current_user.id,
            company_id=active_company.id,
            details={"source": "file_upload", "filename": file.filename},
        )
    db.commit()
    return InvoiceImportOut(created_count=len(created), error_count=0, errors=[], invoices=created)


@router.get("/invoices", response_model=list[InvoiceOut])
def list_invoices(
    status: InvoiceStatus | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    active_company = get_active_company(db, current_user)
    query = select(Invoice).where(Invoice.company_id == active_company.id)
    if status:
        query = query.where(Invoice.status == status)
    invoices = db.scalars(query.order_by(Invoice.created_at.desc())).all()
    return [invoice_to_out(invoice, db) for invoice in invoices]


@router.patch("/invoices/{invoice_id}/status", response_model=InvoiceOut)
def update_invoice_status(
    invoice_id: int,
    payload: InvoiceStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    active_company = get_active_company(db, current_user)
    invoice = db.get(Invoice, invoice_id)
    if not invoice or invoice.company_id != active_company.id:
        raise HTTPException(status_code=404, detail="Invoice not found")
    invoice.status = payload.status
    db.commit()
    db.refresh(invoice)
    return invoice_to_out(invoice, db)


@router.get("/overdue", response_model=list[InvoiceOut])
def get_overdue_invoices(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    active_company = get_active_company(db, current_user)
    invoices = db.scalars(
        select(Invoice).where(
            Invoice.status == InvoiceStatus.PENDING,
            Invoice.company_id == active_company.id,
        )
    ).all()
    return [invoice_to_out(invoice, db) for invoice in invoices if is_overdue(invoice)]


@router.post("/invoices/{invoice_id}/mark-paid", response_model=InvoiceOut)
def mark_invoice_paid_direct(
    invoice_id: int,
    payload: PaymentConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    active_company = get_active_company(db, current_user)
    invoice = db.get(Invoice, invoice_id)
    if not invoice or invoice.company_id != active_company.id:
        raise HTTPException(status_code=404, detail="Invoice not found")
    was_paid = invoice.status == InvoiceStatus.PAID
    mark_invoice_paid(db, invoice, payload.payment_reference)
    if not was_paid:
        record_audit_event(
            db,
            action="invoice_marked_paid",
            entity_type="invoice",
            entity_id=invoice.id,
            user_id=current_user.id,
            company_id=active_company.id,
            details={"payment_reference": invoice.payment_reference or ""},
        )
    return invoice_to_out(invoice, db)


@router.get("/invoices/{invoice_id}/pdf")
def download_invoice_pdf(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    active_company = get_active_company(db, current_user)
    invoice = db.get(Invoice, invoice_id)
    if not invoice or invoice.company_id != active_company.id:
        raise HTTPException(status_code=404, detail="Invoice not found")

    payment_link = build_payment_link(invoice)
    pdf_bytes = build_invoice_pdf(invoice, payment_link, active_company.name)
    record_audit_event(
        db,
        action="invoice_pdf_downloaded",
        entity_type="invoice",
        entity_id=invoice.id,
        user_id=current_user.id,
        company_id=active_company.id,
    )
    headers = {"Content-Disposition": f'attachment; filename="invoice_{invoice.id}.pdf"'}
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)
