from datetime import date, timedelta
from io import StringIO
import csv
import random

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db, run_lightweight_migrations
from app.models import EmailStatus, Invoice, InvoiceStatus, ReminderEmail, User, UserRole
from app.schemas import (
    DashboardStats,
    EmailGenerateRequest,
    IntegrationImportRequest,
    InvoiceCreate,
    InvoiceOut,
    InvoiceStatusUpdate,
    LatePayerInsight,
    ReminderEmailOut,
    ReminderEmailUpdate,
    SendEmailRequest,
    TeamMemberCreate,
    TokenOut,
    UserCreate,
    UserLogin,
    UserOut,
)
from app.security import create_access_token, get_current_user, hash_password, require_admin, verify_password
from app.services import create_pending_reminder, is_overdue, send_reminder_email

Base.metadata.create_all(bind=engine)
run_lightweight_migrations()

app = FastAPI(title="AI Invoice Follow-up Automation API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/auth/signup", response_model=TokenOut)
def signup(payload: UserCreate, db: Session = Depends(get_db)):
    existing = db.scalar(select(User).where((User.email == payload.email) | (User.username == payload.username)))
    if existing:
        raise HTTPException(status_code=400, detail="User with this email or username already exists")

    admin_count = db.scalar(select(func.count()).select_from(User).where(User.role == UserRole.ADMIN)) or 0
    should_be_admin = admin_count == 0
    user = User(
        username=payload.username.strip(),
        email=payload.email.strip().lower(),
        role=UserRole.ADMIN if should_be_admin else UserRole.TEAM,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.email)
    return TokenOut(access_token=token, user=user)


@app.post("/auth/login", response_model=TokenOut)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.strip().lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(user.email)
    return TokenOut(access_token=token, user=user)


@app.get("/auth/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@app.get("/team/users", response_model=list[UserOut])
def list_team_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    users = db.scalars(select(User).order_by(User.created_at.asc())).all()
    return users


@app.post("/team/users", response_model=UserOut)
def create_team_user(payload: TeamMemberCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    existing = db.scalar(select(User).where((User.email == payload.email) | (User.username == payload.username)))
    if existing:
        raise HTTPException(status_code=400, detail="User with this email or username already exists")

    user = User(
        username=payload.username.strip(),
        email=payload.email.strip().lower(),
        role=payload.role,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.get("/integrations/sources")
def list_integration_sources(current_user: User = Depends(get_current_user)):
    return {
        "requested_by": current_user.email,
        "sources": [
            {"id": "fake_api", "mode": "simulated", "ready": True},
            {"id": "xero", "mode": "simulated", "ready": True},
            {"id": "quickbooks", "mode": "simulated", "ready": True},
        ],
    }


@app.post("/integrations/import-invoices", response_model=list[InvoiceOut])
def import_invoices_from_integration(
    payload: IntegrationImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    source_prefix = {
        "fake_api": "Demo",
        "xero": "Xero",
        "quickbooks": "QuickBooks",
    }[payload.source]

    created: list[InvoiceOut] = []
    for idx in range(payload.count):
        amount = round(random.uniform(120, 2500), 2)
        due_offset = random.randint(-20, 15)
        invoice = Invoice(
            user_id=current_user.id,
            customer_name=f"{source_prefix} Customer {idx + 1}",
            customer_email=f"{payload.source}.customer{idx + 1}@example.com",
            amount=amount,
            due_date=date.today() + timedelta(days=due_offset),
            status=InvoiceStatus.PENDING,
        )
        db.add(invoice)
        db.flush()
        created.append(InvoiceOut(**invoice.__dict__, is_overdue=is_overdue(invoice)))

    db.commit()
    return created


@app.post("/invoices", response_model=InvoiceOut)
def create_invoice(
    payload: InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    invoice = Invoice(**payload.model_dump(), user_id=current_user.id)
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return InvoiceOut(**invoice.__dict__, is_overdue=is_overdue(invoice))


@app.post("/invoices/upload-csv", response_model=list[InvoiceOut])
def upload_invoices_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file")

    content = file.file.read().decode("utf-8")
    reader = csv.DictReader(StringIO(content))
    created: list[InvoiceOut] = []

    required_fields = {"customer_name", "customer_email", "amount", "due_date"}
    if not required_fields.issubset(set(reader.fieldnames or [])):
        raise HTTPException(
            status_code=400,
            detail="CSV must include customer_name, customer_email, amount, due_date",
        )

    for row in reader:
        try:
            invoice = Invoice(
                user_id=current_user.id,
                customer_name=row["customer_name"].strip(),
                customer_email=row["customer_email"].strip(),
                amount=float(row["amount"]),
                due_date=date.fromisoformat(row["due_date"]),
            )
        except Exception:
            continue

        db.add(invoice)
        db.flush()
        created.append(InvoiceOut(**invoice.__dict__, is_overdue=is_overdue(invoice)))

    db.commit()
    return created


@app.get("/invoices", response_model=list[InvoiceOut])
def list_invoices(
    status: InvoiceStatus | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Invoice).where(Invoice.user_id == current_user.id)
    if status:
        query = query.where(Invoice.status == status)

    invoices = db.scalars(query.order_by(Invoice.created_at.desc())).all()
    return [InvoiceOut(**invoice.__dict__, is_overdue=is_overdue(invoice)) for invoice in invoices]


@app.patch("/invoices/{invoice_id}/status", response_model=InvoiceOut)
def update_invoice_status(
    invoice_id: int,
    payload: InvoiceStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    invoice = db.get(Invoice, invoice_id)
    if not invoice or invoice.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Invoice not found")

    invoice.status = payload.status
    db.commit()
    db.refresh(invoice)
    return InvoiceOut(**invoice.__dict__, is_overdue=is_overdue(invoice))


@app.get("/overdue", response_model=list[InvoiceOut])
def get_overdue_invoices(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    invoices = db.scalars(
        select(Invoice).where(Invoice.status == InvoiceStatus.PENDING, Invoice.user_id == current_user.id)
    ).all()
    overdue = [invoice for invoice in invoices if is_overdue(invoice)]
    return [InvoiceOut(**invoice.__dict__, is_overdue=True) for invoice in overdue]


@app.post("/generate-email", response_model=ReminderEmailOut)
def generate_email(
    payload: EmailGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    invoice = db.get(Invoice, payload.invoice_id)
    if not invoice or invoice.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status == InvoiceStatus.PAID:
        raise HTTPException(status_code=400, detail="Cannot generate reminder for a paid invoice")

    reminder = create_pending_reminder(db, invoice, payload.tone, current_user.id)
    return reminder


@app.get("/emails/pending-approvals", response_model=list[ReminderEmailOut])
def pending_approvals(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    reminders = db.scalars(
        select(ReminderEmail)
        .where(ReminderEmail.status == EmailStatus.PENDING_APPROVAL, ReminderEmail.user_id == current_user.id)
        .order_by(ReminderEmail.created_at.desc())
    ).all()
    return reminders


@app.get("/emails", response_model=list[ReminderEmailOut])
def list_emails(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    reminders = db.scalars(
        select(ReminderEmail)
        .where(ReminderEmail.user_id == current_user.id)
        .order_by(ReminderEmail.created_at.desc())
    ).all()
    return reminders


@app.patch("/emails/{email_id}/edit", response_model=ReminderEmailOut)
def edit_email(
    email_id: int,
    payload: ReminderEmailUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    reminder = db.get(ReminderEmail, email_id)
    if not reminder or reminder.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Email not found")

    if reminder.status != EmailStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=400, detail="Only pending approval emails can be edited")

    reminder.subject = payload.subject
    reminder.body = payload.body
    db.commit()
    db.refresh(reminder)
    return reminder


@app.post("/emails/{email_id}/approve", response_model=ReminderEmailOut)
def approve_email(
    email_id: int,
    payload: SendEmailRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    reminder = db.get(ReminderEmail, email_id)
    if not reminder or reminder.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Email not found")

    if reminder.status != EmailStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=400, detail="Email is not pending approval")

    reminder.status = EmailStatus.APPROVED
    db.commit()
    db.refresh(reminder)

    return send_reminder_email(db, reminder, payload.provider)


@app.post("/emails/{email_id}/send", response_model=ReminderEmailOut)
def send_email_direct(
    email_id: int,
    payload: SendEmailRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    reminder = db.get(ReminderEmail, email_id)
    if not reminder or reminder.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Email not found")

    if reminder.status not in {EmailStatus.PENDING_APPROVAL, EmailStatus.APPROVED, EmailStatus.FAILED}:
        raise HTTPException(status_code=400, detail="Email cannot be sent in current state")

    return send_reminder_email(db, reminder, payload.provider)


@app.post("/emails/{email_id}/reject", response_model=ReminderEmailOut)
def reject_email(email_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    reminder = db.get(ReminderEmail, email_id)
    if not reminder or reminder.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Email not found")

    if reminder.status != EmailStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=400, detail="Email is not pending approval")

    reminder.status = EmailStatus.REJECTED
    db.commit()
    db.refresh(reminder)
    return reminder


@app.get("/dashboard/stats", response_model=DashboardStats)
def dashboard_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    total_invoices = db.scalar(
        select(func.count()).select_from(Invoice).where(Invoice.user_id == current_user.id)
    ) or 0
    pending_invoices = db.scalars(
        select(Invoice).where(Invoice.status == InvoiceStatus.PENDING, Invoice.user_id == current_user.id)
    ).all()
    overdue_invoices = sum(1 for inv in pending_invoices if is_overdue(inv))
    emails_sent = db.scalar(
        select(func.count())
        .select_from(ReminderEmail)
        .where(ReminderEmail.status == EmailStatus.SENT, ReminderEmail.user_id == current_user.id)
    ) or 0
    pending_approvals = db.scalar(
        select(func.count())
        .select_from(ReminderEmail)
        .where(ReminderEmail.status == EmailStatus.PENDING_APPROVAL, ReminderEmail.user_id == current_user.id)
    ) or 0

    return DashboardStats(
        total_invoices=total_invoices,
        overdue_invoices=overdue_invoices,
        emails_sent=emails_sent,
        pending_approvals=pending_approvals,
    )


@app.get("/insights/late-payers", response_model=list[LatePayerInsight])
def late_payer_insights(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    invoices = db.scalars(select(Invoice).where(Invoice.user_id == current_user.id)).all()
    if not invoices:
        return []

    groups: dict[str, dict[str, object]] = {}
    for invoice in invoices:
        key = invoice.customer_email.strip().lower()
        group = groups.setdefault(
            key,
            {
                "customer_name": invoice.customer_name,
                "customer_email": invoice.customer_email,
                "total": 0,
                "overdue": 0,
            },
        )

        group["total"] = int(group["total"]) + 1
        if invoice.status == InvoiceStatus.PENDING and invoice.due_date < date.today():
            group["overdue"] = int(group["overdue"]) + 1

    insights: list[LatePayerInsight] = []
    for data in groups.values():
        total = int(data["total"])
        overdue = int(data["overdue"])
        if total == 0 or overdue == 0:
            continue

        overdue_rate = round((overdue / total) * 100, 1)
        if overdue_rate >= 60:
            risk_level = "high"
            insight = "Frequent payment delays. Prioritize proactive reminders and stricter follow-up."
        elif overdue_rate >= 30:
            risk_level = "medium"
            insight = "Occasional payment delays. Consider sending reminders earlier than due date."
        else:
            risk_level = "low"
            insight = "Rare payment delays. Standard reminder cadence is typically sufficient."

        insights.append(
            LatePayerInsight(
                customer_name=str(data["customer_name"]),
                customer_email=str(data["customer_email"]),
                total_invoices=total,
                overdue_invoices=overdue,
                overdue_rate=overdue_rate,
                risk_level=risk_level,
                insight=insight,
            )
        )

    insights.sort(key=lambda item: (item.overdue_rate, item.overdue_invoices), reverse=True)
    return insights[:5]
