import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import date, datetime, timedelta
from io import StringIO
import csv
import random
import base64
import secrets
from urllib.parse import urlencode

import httpx

from fastapi import Depends, FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import Base, SessionLocal, engine, get_db, run_lightweight_migrations
from app.models import Company, CompanyMembership, EmailStatus, IntegrationConnection, Invoice, InvoiceStatus, ReminderEmail, User, UserRole
from app.schemas import (
    CompanyCreate,
    CompanyInviteRequest,
    CompanyMemberRemoveRequest,
    CompanyOut,
    CompanySwitchRequest,
    CustomerHistoryOut,
    DashboardStats,
    CustomerHistoryTrendPoint,
    EmailGenerateRequest,
    IntegrationConnectorOut,
    IntegrationOAuthCallbackRequest,
    IntegrationOAuthStartOut,
    IntegrationImportRequest,
    IntegrationSyncRequest,
    InvoiceCreate,
    InvoiceOut,
    InvoiceStatusUpdate,
    LatePayerInsight,
    PaymentConfirmRequest,
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
from app.services import (
    build_payment_link,
    create_pending_reminder,
    ensure_payment_token,
    is_overdue,
    mark_email_opened,
    mark_invoice_paid,
    run_automation_cycle,
    send_reminder_email,
)

Base.metadata.create_all(bind=engine)
run_lightweight_migrations()


async def _automation_loop() -> None:
    settings = get_settings()
    interval_seconds = max(1, settings.automation_interval_minutes) * 60

    while True:
        if settings.automation_enabled:
            db = SessionLocal()
            try:
                run_automation_cycle(db)
            except Exception:
                pass
            finally:
                db.close()

        await asyncio.sleep(interval_seconds)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(_automation_loop())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="AI Invoice Follow-up Automation API", version="1.0.0", lifespan=lifespan)

TRACKING_GIF = base64.b64decode("R0lGODlhAQABAIABAP///wAAACwAAAAAAQABAAACAkQBADs=")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def invoice_to_out(invoice: Invoice, db: Session) -> InvoiceOut:
    ensure_payment_token(db, invoice)
    return InvoiceOut(
        id=invoice.id,
        customer_name=invoice.customer_name,
        customer_email=invoice.customer_email,
        amount=invoice.amount,
        due_date=invoice.due_date,
        status=invoice.status,
        is_overdue=is_overdue(invoice),
        payment_url=build_payment_link(invoice),
        payment_reference=invoice.payment_reference,
        paid_at=invoice.paid_at,
    )


def _month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def _month_label(month_key: str) -> str:
    year, month = month_key.split("-")
    month_start = date(int(year), int(month), 1)
    return month_start.strftime("%b %Y")


def _invoice_days_late(invoice: Invoice) -> int:
    if invoice.status == InvoiceStatus.PAID and invoice.paid_at:
        paid_date = invoice.paid_at.date()
        return max(0, (paid_date - invoice.due_date).days)
    if invoice.status == InvoiceStatus.PENDING and invoice.due_date < date.today():
        return (date.today() - invoice.due_date).days
    return 0


def _risk_score(overdue_rate: float, late_paid_rate: float, outstanding_rate: float) -> float:
    score = (overdue_rate * 0.55) + (late_paid_rate * 0.3) + (outstanding_rate * 0.15)
    return round(min(100.0, max(0.0, score)), 1)


def _risk_level(score: float) -> str:
    if score >= 65:
        return "high"
    if score >= 35:
        return "medium"
    return "low"


def _default_company_name(user: User) -> str:
    return f"{user.username} Company"


INTEGRATION_PROVIDERS: dict[str, str] = {
    "xero": "Xero",
    "quickbooks": "QuickBooks",
    "zoho_books": "Zoho Books",
}


def _build_integration_auth_url(provider: str, state: str) -> str:
    settings = get_settings()
    if provider == "quickbooks" and settings.quickbooks_client_id:
        params = urlencode(
            {
                "client_id": settings.quickbooks_client_id,
                "response_type": "code",
                "scope": settings.quickbooks_scope,
                "redirect_uri": settings.integration_redirect_base_url,
                "state": state,
            }
        )
        return f"{settings.quickbooks_auth_url}?{params}"

    redirect = settings.integration_redirect_base_url.rstrip("/")
    return f"{redirect}?provider={provider}&state={state}"


def _integration_mode(provider: str) -> str:
    settings = get_settings()
    if provider == "quickbooks" and settings.quickbooks_client_id and settings.quickbooks_client_secret:
        return "oauth_live"
    return "oauth_scaffold"


def _exchange_quickbooks_code(code: str) -> tuple[str, str | None]:
    settings = get_settings()
    if not settings.quickbooks_client_id or not settings.quickbooks_client_secret:
        raise HTTPException(status_code=400, detail="QuickBooks OAuth credentials are not configured")

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.integration_redirect_base_url,
    }

    with httpx.Client(timeout=20.0) as client:
        response = client.post(
            settings.quickbooks_token_url,
            data=data,
            auth=(settings.quickbooks_client_id, settings.quickbooks_client_secret),
            headers={"Accept": "application/json"},
        )

    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"QuickBooks token exchange failed: {response.text}")

    payload = response.json()
    access_token = payload.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="QuickBooks token exchange returned no access_token")

    return str(access_token), str(payload.get("refresh_token") or "") or None


def _get_or_create_integration_connection(db: Session, company_id: int, provider: str) -> IntegrationConnection:
    connection = db.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.company_id == company_id,
            IntegrationConnection.provider == provider,
        )
    )
    if connection:
        return connection

    connection = IntegrationConnection(company_id=company_id, provider=provider, connected=0)
    db.add(connection)
    db.flush()
    return connection


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
    member_ids = db.scalars(
        select(CompanyMembership.company_id).where(CompanyMembership.user_id == user.id)
    ).all()
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

    # Backfill legacy records that predate company scoping.
    db.query(Invoice).filter(Invoice.user_id == user.id, Invoice.company_id.is_(None)).update(
        {Invoice.company_id: active.id},
        synchronize_session=False,
    )
    db.query(ReminderEmail).filter(
        ReminderEmail.user_id == user.id,
        ReminderEmail.company_id.is_(None),
    ).update(
        {ReminderEmail.company_id: active.id},
        synchronize_session=False,
    )

    db.commit()
    db.refresh(user)
    db.refresh(active)
    return active


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/automation/run-now")
def automation_run_now(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return run_automation_cycle(db)


@app.get("/emails/track/open/{token}.gif")
def track_email_open(token: str, db: Session = Depends(get_db)):
    mark_email_opened(db, token)
    return Response(content=TRACKING_GIF, media_type="image/gif")


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

    default_company = Company(owner_user_id=user.id, name=_default_company_name(user))
    db.add(default_company)
    db.flush()
    db.add(CompanyMembership(company_id=default_company.id, user_id=user.id))
    user.active_company_id = default_company.id
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
def me(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    get_active_company(db, current_user)
    return current_user


@app.get("/companies", response_model=list[CompanyOut])
def list_companies(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    get_active_company(db, current_user)
    return _get_accessible_companies(db, current_user)


@app.post("/companies", response_model=CompanyOut)
def create_company(
    payload: CompanyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_active_company(db, current_user)
    company = Company(owner_user_id=current_user.id, name=payload.name.strip())
    db.add(company)
    db.flush()
    db.add(CompanyMembership(company_id=company.id, user_id=current_user.id))
    db.commit()
    db.refresh(company)
    return company


@app.post("/companies/switch", response_model=UserOut)
def switch_company(
    payload: CompanySwitchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    company = db.scalar(select(Company).where(Company.id == payload.company_id))
    if company and not _company_accessible(db, current_user, company.id):
        company = None
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    current_user.active_company_id = company.id
    db.commit()
    db.refresh(current_user)
    return current_user


@app.post("/companies/active/invite", response_model=UserOut)
def invite_existing_user_to_active_company(
    payload: CompanyInviteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    active_company = get_active_company(db, current_user)
    invited_user = db.scalar(select(User).where(User.email == payload.email.strip().lower()))
    if not invited_user:
        raise HTTPException(status_code=404, detail="User not found")

    membership = db.scalar(
        select(CompanyMembership).where(
            CompanyMembership.company_id == active_company.id,
            CompanyMembership.user_id == invited_user.id,
        )
    )
    if membership:
        raise HTTPException(status_code=400, detail="User is already a member of this company")

    db.add(CompanyMembership(company_id=active_company.id, user_id=invited_user.id))
    if not invited_user.active_company_id:
        invited_user.active_company_id = active_company.id

    db.commit()
    db.refresh(invited_user)
    return invited_user


@app.post("/companies/active/remove-member", response_model=UserOut)
def remove_member_from_active_company(
    payload: CompanyMemberRemoveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    active_company = get_active_company(db, current_user)
    target_user = db.get(User, payload.user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    if target_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot remove yourself from the active company")

    if target_user.id == active_company.owner_user_id:
        raise HTTPException(status_code=400, detail="Company owner cannot be removed")

    membership = db.scalar(
        select(CompanyMembership).where(
            CompanyMembership.company_id == active_company.id,
            CompanyMembership.user_id == target_user.id,
        )
    )
    if not membership:
        raise HTTPException(status_code=404, detail="User is not a member of this company")

    db.delete(membership)
    if target_user.active_company_id == active_company.id:
        target_user.active_company_id = None
    db.commit()
    db.refresh(target_user)
    return target_user


@app.get("/team/users", response_model=list[UserOut])
def list_team_users(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    active_company = get_active_company(db, current_user)
    member_ids = db.scalars(
        select(CompanyMembership.user_id).where(CompanyMembership.company_id == active_company.id)
    ).all()
    if active_company.owner_user_id not in member_ids:
        member_ids = [*member_ids, active_company.owner_user_id]

    users = db.scalars(select(User).where(User.id.in_(member_ids)).order_by(User.created_at.asc())).all()
    return users


@app.post("/team/users", response_model=UserOut)
def create_team_user(payload: TeamMemberCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    active_company = get_active_company(db, current_user)
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
    db.flush()
    db.add(CompanyMembership(company_id=active_company.id, user_id=user.id))
    user.active_company_id = active_company.id
    db.commit()
    db.refresh(user)
    return user


@app.get("/integrations/sources")
def list_integration_sources(current_user: User = Depends(get_current_user)):
    return {
        "requested_by": current_user.email,
        "sources": [
            {"id": "fake_api", "mode": "simulated", "ready": True},
            {"id": "xero", "mode": "oauth_scaffold", "ready": True},
            {"id": "quickbooks", "mode": "oauth_scaffold", "ready": True},
            {"id": "zoho_books", "mode": "oauth_scaffold", "ready": True},
        ],
    }


@app.get("/integrations/connectors", response_model=list[IntegrationConnectorOut])
def list_integration_connectors(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    active_company = get_active_company(db, current_user)
    output: list[IntegrationConnectorOut] = []

    for provider, display_name in INTEGRATION_PROVIDERS.items():
        connection = db.scalar(
            select(IntegrationConnection).where(
                IntegrationConnection.company_id == active_company.id,
                IntegrationConnection.provider == provider,
            )
        )

        output.append(
            IntegrationConnectorOut(
                provider=provider,
                display_name=display_name,
                connected=bool(connection.connected) if connection else False,
                mode=_integration_mode(provider),
                auth_url=_build_integration_auth_url(provider, connection.oauth_state if connection and connection.oauth_state else "pending"),
                last_synced_at=connection.last_synced_at if connection else None,
                last_error=connection.last_error if connection else None,
            )
        )

    return output


@app.post("/integrations/{provider}/oauth/start", response_model=IntegrationOAuthStartOut)
def start_integration_oauth(provider: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    provider = provider.lower()
    if provider not in INTEGRATION_PROVIDERS:
        raise HTTPException(status_code=400, detail="Unsupported integration provider")

    active_company = get_active_company(db, current_user)
    state = secrets.token_urlsafe(16)
    connection = _get_or_create_integration_connection(db, active_company.id, provider)
    connection.oauth_state = state
    connection.last_error = None
    connection.updated_at = datetime.utcnow()
    db.commit()

    return IntegrationOAuthStartOut(provider=provider, auth_url=_build_integration_auth_url(provider, state), state=state)


@app.post("/integrations/{provider}/oauth/callback", response_model=IntegrationConnectorOut)
def complete_integration_oauth(
    provider: str,
    payload: IntegrationOAuthCallbackRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    provider = provider.lower()
    if provider not in INTEGRATION_PROVIDERS:
        raise HTTPException(status_code=400, detail="Unsupported integration provider")

    active_company = get_active_company(db, current_user)
    connection = _get_or_create_integration_connection(db, active_company.id, provider)
    if not connection.oauth_state or connection.oauth_state != payload.state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    now = datetime.utcnow()
    if provider == "quickbooks" and _integration_mode(provider) == "oauth_live" and payload.code != "demo-code":
        access_token, refresh_token = _exchange_quickbooks_code(payload.code)
        connection.access_token = access_token
        connection.refresh_token = refresh_token
    else:
        connection.access_token = f"{provider}_access_{secrets.token_hex(8)}"
        connection.refresh_token = f"{provider}_refresh_{secrets.token_hex(8)}"

    connection.connected = 1
    connection.oauth_state = None
    connection.last_error = None
    connection.updated_at = now
    db.commit()
    db.refresh(connection)

    return IntegrationConnectorOut(
        provider=provider,
        display_name=INTEGRATION_PROVIDERS[provider],
        connected=True,
        mode=_integration_mode(provider),
        auth_url=_build_integration_auth_url(provider, "connected"),
        last_synced_at=connection.last_synced_at,
        last_error=connection.last_error,
    )


@app.post("/integrations/{provider}/disconnect", response_model=IntegrationConnectorOut)
def disconnect_integration(provider: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    provider = provider.lower()
    if provider not in INTEGRATION_PROVIDERS:
        raise HTTPException(status_code=400, detail="Unsupported integration provider")

    active_company = get_active_company(db, current_user)
    connection = _get_or_create_integration_connection(db, active_company.id, provider)
    connection.connected = 0
    connection.oauth_state = None
    connection.access_token = None
    connection.refresh_token = None
    connection.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(connection)

    return IntegrationConnectorOut(
        provider=provider,
        display_name=INTEGRATION_PROVIDERS[provider],
        connected=False,
        mode=_integration_mode(provider),
        auth_url=_build_integration_auth_url(provider, "disconnected"),
        last_synced_at=connection.last_synced_at,
        last_error=connection.last_error,
    )


@app.post("/integrations/{provider}/sync-invoices", response_model=list[InvoiceOut])
def sync_integration_invoices(
    provider: str,
    payload: IntegrationSyncRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    provider = provider.lower()
    if provider not in INTEGRATION_PROVIDERS:
        raise HTTPException(status_code=400, detail="Unsupported integration provider")

    active_company = get_active_company(db, current_user)
    connection = _get_or_create_integration_connection(db, active_company.id, provider)
    if not connection.connected:
        raise HTTPException(status_code=400, detail=f"{INTEGRATION_PROVIDERS[provider]} is not connected")

    created: list[InvoiceOut] = []
    for idx in range(payload.count):
        amount = round(random.uniform(90, 2200), 2)
        due_offset = random.randint(-15, 20)
        invoice = Invoice(
            user_id=current_user.id,
            company_id=active_company.id,
            customer_name=f"{INTEGRATION_PROVIDERS[provider]} Sync Customer {idx + 1}",
            customer_email=f"{provider}.sync{idx + 1}@example.com",
            amount=amount,
            due_date=date.today() + timedelta(days=due_offset),
            status=InvoiceStatus.PENDING,
        )
        db.add(invoice)
        db.flush()
        created.append(invoice_to_out(invoice, db))

    connection.last_synced_at = datetime.utcnow()
    connection.last_error = None
    connection.updated_at = datetime.utcnow()
    db.commit()
    return created


@app.post("/integrations/import-invoices", response_model=list[InvoiceOut])
def import_invoices_from_integration(
    payload: IntegrationImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    active_company = get_active_company(db, current_user)
    source_prefix = {
        "fake_api": "Demo",
        "xero": "Xero",
        "quickbooks": "QuickBooks",
        "zoho_books": "Zoho Books",
    }[payload.source]

    created: list[InvoiceOut] = []
    for idx in range(payload.count):
        amount = round(random.uniform(120, 2500), 2)
        due_offset = random.randint(-20, 15)
        invoice = Invoice(
            user_id=current_user.id,
            company_id=active_company.id,
            customer_name=f"{source_prefix} Customer {idx + 1}",
            customer_email=f"{payload.source}.customer{idx + 1}@example.com",
            amount=amount,
            due_date=date.today() + timedelta(days=due_offset),
            status=InvoiceStatus.PENDING,
        )
        db.add(invoice)
        db.flush()
        created.append(invoice_to_out(invoice, db))

    db.commit()
    return created


@app.post("/invoices", response_model=InvoiceOut)
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
    return invoice_to_out(invoice, db)


@app.post("/invoices/upload-csv", response_model=list[InvoiceOut])
def upload_invoices_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    active_company = get_active_company(db, current_user)
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
                company_id=active_company.id,
                customer_name=row["customer_name"].strip(),
                customer_email=row["customer_email"].strip(),
                amount=float(row["amount"]),
                due_date=date.fromisoformat(row["due_date"]),
            )
        except Exception:
            continue

        db.add(invoice)
        db.flush()
        created.append(invoice_to_out(invoice, db))

    db.commit()
    return created


@app.get("/invoices", response_model=list[InvoiceOut])
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


@app.patch("/invoices/{invoice_id}/status", response_model=InvoiceOut)
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


@app.get("/overdue", response_model=list[InvoiceOut])
def get_overdue_invoices(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    active_company = get_active_company(db, current_user)
    invoices = db.scalars(
        select(Invoice).where(
            Invoice.status == InvoiceStatus.PENDING,
            Invoice.company_id == active_company.id,
        )
    ).all()
    overdue = [invoice for invoice in invoices if is_overdue(invoice)]
    return [invoice_to_out(invoice, db) for invoice in overdue]


@app.post("/invoices/{invoice_id}/mark-paid", response_model=InvoiceOut)
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

    mark_invoice_paid(db, invoice, payload.payment_reference)
    return invoice_to_out(invoice, db)


@app.post("/payments/confirm/{token}", response_model=InvoiceOut)
def confirm_payment_by_token(token: str, payload: PaymentConfirmRequest, db: Session = Depends(get_db)):
    invoice = db.scalar(select(Invoice).where(Invoice.payment_token == token))
    if not invoice:
        raise HTTPException(status_code=404, detail="Payment token not found")

    mark_invoice_paid(db, invoice, payload.payment_reference)
    return invoice_to_out(invoice, db)


@app.get("/payments/pay/{token}", response_class=HTMLResponse)
def payment_checkout_page(token: str, db: Session = Depends(get_db)):
    invoice = db.scalar(select(Invoice).where(Invoice.payment_token == token))
    if not invoice:
        raise HTTPException(status_code=404, detail="Payment token not found")

    status_text = "PAID" if invoice.status == InvoiceStatus.PAID else "PENDING"
    paid_notice = (
        f"<p><strong>Paid at:</strong> {invoice.paid_at}</p><p><strong>Reference:</strong> {invoice.payment_reference}</p>"
        if invoice.status == InvoiceStatus.PAID
        else ""
    )

    return f"""
    <html>
      <head><title>Invoice Payment</title></head>
      <body style='font-family: Arial, sans-serif; max-width: 680px; margin: 24px auto; padding: 16px;'>
        <h2>Invoice #{invoice.id} Payment</h2>
        <p><strong>Customer:</strong> {invoice.customer_name}</p>
        <p><strong>Amount:</strong> ${invoice.amount:,.2f}</p>
        <p><strong>Status:</strong> {status_text}</p>
        {paid_notice}
        <form method='post' action='/payments/confirm-form/{token}'>
          <label>Payment Reference:</label><br/>
          <input name='payment_reference' value='DEMO-{invoice.id}' style='padding:8px; width: 260px; margin-top: 6px;' required />
          <br/><br/>
          <button type='submit' style='padding: 10px 16px;'>Pay Now</button>
        </form>
      </body>
    </html>
    """


@app.post("/payments/confirm-form/{token}", response_class=HTMLResponse)
def confirm_payment_form(token: str, payment_reference: str = Form(...), db: Session = Depends(get_db)):
    invoice = db.scalar(select(Invoice).where(Invoice.payment_token == token))
    if not invoice:
        raise HTTPException(status_code=404, detail="Payment token not found")

    mark_invoice_paid(db, invoice, payment_reference)
    return (
        "<html><body style='font-family: Arial, sans-serif; max-width:680px; margin: 24px auto;'>"
        "<h3>Payment recorded successfully.</h3>"
        f"<p>Invoice #{invoice.id} is now marked as paid with reference <strong>{invoice.payment_reference}</strong>.</p>"
        "</body></html>"
    )


@app.post("/generate-email", response_model=ReminderEmailOut)
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

    reminder = create_pending_reminder(db, invoice, payload.tone, current_user.id, active_company.id)
    return reminder


@app.get("/emails/pending-approvals", response_model=list[ReminderEmailOut])
def pending_approvals(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    active_company = get_active_company(db, current_user)
    reminders = db.scalars(
        select(ReminderEmail)
        .where(
            ReminderEmail.status == EmailStatus.PENDING_APPROVAL,
            ReminderEmail.company_id == active_company.id,
        )
        .order_by(ReminderEmail.created_at.desc())
    ).all()
    return reminders


@app.get("/emails", response_model=list[ReminderEmailOut])
def list_emails(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    active_company = get_active_company(db, current_user)
    reminders = db.scalars(
        select(ReminderEmail)
        .where(ReminderEmail.company_id == active_company.id)
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


@app.post("/emails/{email_id}/approve", response_model=ReminderEmailOut)
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

    return send_reminder_email(db, reminder, payload.provider)


@app.post("/emails/{email_id}/send", response_model=ReminderEmailOut)
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

    return send_reminder_email(db, reminder, payload.provider)


@app.post("/emails/{email_id}/reject", response_model=ReminderEmailOut)
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
    return reminder


@app.get("/dashboard/stats", response_model=DashboardStats)
def dashboard_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    active_company = get_active_company(db, current_user)
    total_invoices = db.scalar(
        select(func.count())
        .select_from(Invoice)
        .where(Invoice.company_id == active_company.id)
    ) or 0
    pending_invoices = db.scalars(
        select(Invoice).where(
            Invoice.status == InvoiceStatus.PENDING,
            Invoice.company_id == active_company.id,
        )
    ).all()
    overdue_invoices = sum(1 for inv in pending_invoices if is_overdue(inv))
    emails_sent = db.scalar(
        select(func.count())
        .select_from(ReminderEmail)
        .where(
            ReminderEmail.status.in_([EmailStatus.SENT, EmailStatus.DELIVERED, EmailStatus.OPENED]),
            ReminderEmail.company_id == active_company.id,
        )
    ) or 0
    pending_approvals = db.scalar(
        select(func.count())
        .select_from(ReminderEmail)
        .where(
            ReminderEmail.status == EmailStatus.PENDING_APPROVAL,
            ReminderEmail.company_id == active_company.id,
        )
    ) or 0

    return DashboardStats(
        total_invoices=total_invoices,
        overdue_invoices=overdue_invoices,
        emails_sent=emails_sent,
        pending_approvals=pending_approvals,
    )


@app.get("/insights/late-payers", response_model=list[LatePayerInsight])
def late_payer_insights(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    active_company = get_active_company(db, current_user)
    invoices = db.scalars(
        select(Invoice).where(Invoice.company_id == active_company.id)
    ).all()
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


@app.get("/customers/history", response_model=list[CustomerHistoryOut])
def customer_history(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    active_company = get_active_company(db, current_user)
    invoices = db.scalars(
        select(Invoice)
        .where(Invoice.company_id == active_company.id)
        .order_by(Invoice.due_date.asc())
    ).all()
    if not invoices:
        return []

    groups: dict[str, list[Invoice]] = {}
    for invoice in invoices:
        key = invoice.customer_email.strip().lower()
        groups.setdefault(key, []).append(invoice)

    now = datetime.utcnow().date()
    output: list[CustomerHistoryOut] = []

    for _, items in groups.items():
        total = len(items)
        paid_items = [item for item in items if item.status == InvoiceStatus.PAID]
        paid_count = len(paid_items)
        overdue_count = sum(
            1
            for item in items
            if item.status == InvoiceStatus.PENDING and item.due_date < now
        )
        outstanding_amount = round(
            sum(item.amount for item in items if item.status != InvoiceStatus.PAID),
            2,
        )

        on_time_paid = sum(
            1
            for item in paid_items
            if item.paid_at and item.paid_at.date() <= item.due_date
        )
        on_time_rate = round((on_time_paid / paid_count) * 100, 1) if paid_count else 0.0

        late_values = [_invoice_days_late(item) for item in paid_items]
        average_days_late = round(sum(late_values) / len(late_values), 1) if late_values else 0.0

        monthly_groups: dict[str, list[Invoice]] = {}
        for item in items:
            monthly_groups.setdefault(_month_key(item.due_date), []).append(item)

        sorted_months = sorted(monthly_groups.keys())[-6:]
        trend: list[CustomerHistoryTrendPoint] = []
        for month in sorted_months:
            month_items = monthly_groups[month]
            month_total = len(month_items)
            month_overdue = sum(
                1
                for item in month_items
                if item.status == InvoiceStatus.PENDING and item.due_date < now
            )
            month_paid = [item for item in month_items if item.status == InvoiceStatus.PAID]
            month_late_paid = sum(
                1
                for item in month_paid
                if item.paid_at and item.paid_at.date() > item.due_date
            )
            month_overdue_rate = (month_overdue / month_total) * 100 if month_total else 0.0
            month_late_paid_rate = (month_late_paid / month_total) * 100 if month_total else 0.0
            month_outstanding_rate = (
                (sum(item.amount for item in month_items if item.status != InvoiceStatus.PAID) /
                 max(1.0, sum(item.amount for item in month_items))) * 100
            )

            trend.append(
                CustomerHistoryTrendPoint(
                    month=_month_label(month),
                    risk_score=_risk_score(month_overdue_rate, month_late_paid_rate, month_outstanding_rate),
                )
            )

        overdue_rate = (overdue_count / total) * 100 if total else 0.0
        late_paid_count = sum(
            1
            for item in paid_items
            if item.paid_at and item.paid_at.date() > item.due_date
        )
        late_paid_rate = (late_paid_count / total) * 100 if total else 0.0
        total_amount = max(1.0, sum(item.amount for item in items))
        outstanding_rate = (outstanding_amount / total_amount) * 100

        risk_score = _risk_score(overdue_rate, late_paid_rate, outstanding_rate)

        output.append(
            CustomerHistoryOut(
                customer_name=items[-1].customer_name,
                customer_email=items[-1].customer_email,
                total_invoices=total,
                paid_invoices=paid_count,
                overdue_invoices=overdue_count,
                outstanding_amount=outstanding_amount,
                on_time_payment_rate=on_time_rate,
                average_days_late=average_days_late,
                risk_score=risk_score,
                risk_level=_risk_level(risk_score),
                trend=trend,
            )
        )

    output.sort(key=lambda item: (item.risk_score, item.outstanding_amount), reverse=True)
    return output
