import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import date, datetime, timedelta, timezone
import random
import base64
import secrets
import logging
import json
from collections import defaultdict, deque
from html import escape
from urllib.parse import urlencode
from typing import Any

import httpx
try:
    import redis as redis_lib
except Exception:  # pragma: no cover
    redis_lib = None

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.api.routes.auth import router as auth_router
from app.api.routes.emails import router as email_router
from app.api.routes.invoices import router as invoice_router
from app.database import Base, SessionLocal, engine, get_db, run_lightweight_migrations
from app.invoice_import import parse_invoice_file, validate_invoice_rows
from app.models import (
    AuditLog,
    Company,
    CompanyMembership,
    EmailStatus,
    IntegrationConnection,
    Invoice,
    InvoiceStatus,
    JobQueue,
    RefreshToken,
    ReminderEmail,
    RevokedAccessToken,
    User,
    UserRole,
    WebhookEvent,
)
from app.schemas import (
    AutomationStatusOut,
    AuditLogOut,
    CompanyCreate,
    CompanyInviteRequest,
    CompanyMemberRemoveRequest,
    CompanyOut,
    CompanySwitchRequest,
    CustomerHistoryOut,
    DashboardStats,
    CustomerHistoryTrendPoint,
    EmailGenerateRequest,
    InvoiceImportOut,
    IntegrationConnectorOut,
    IntegrationOAuthCallbackRequest,
    IntegrationOAuthStartOut,
    IntegrationImportRequest,
    IntegrationSyncRequest,
    InvoiceCreate,
    InvoiceOut,
    InvoiceStatusUpdate,
    LatePayerInsight,
    OpsMetricsOut,
    PaymentConfirmRequest,
    PaymentWebhookIn,
    QueueStatsOut,
    ReportsOverviewOut,
    ReminderEmailOut,
    ReminderEmailUpdate,
    SendEmailRequest,
    TopLatePayerOut,
    TeamMemberCreate,
    TokenOut,
    TokenRefreshRequest,
    TwilioStatusWebhookIn,
    LogoutRequest,
    MfaEnableRequest,
    MfaSetupOut,
    UserCreate,
    UserLogin,
    JobQueueOut,
    UserOut,
    EmailStatusWebhookIn,
    WebhookAckOut,
)
from app.scheduler import AutomationScheduler
from app.security import (
    create_access_token,
    decode_access_token,
    generate_mfa_secret,
    get_current_user,
    hash_password,
    hash_refresh_token,
    refresh_token_raw,
    require_admin,
    verify_password,
    verify_totp,
    bearer_scheme,
)
from app.services import (
    build_payment_link,
    create_pending_reminder,
    ensure_payment_token,
    is_overdue,
    mark_email_clicked,
    mark_email_opened,
    mark_invoice_paid,
    run_automation_cycle,
    send_reminder_email,
)

Base.metadata.create_all(bind=engine)
run_lightweight_migrations()
logger = logging.getLogger(__name__)
_RATE_LIMIT_BUCKETS: dict[str, deque[float]] = defaultdict(deque)
_AUTH_RATE_LIMIT_PATHS = {"/auth/login", "/auth/signup"}
_REDIS_CLIENT: Any = None
_SCHEDULER: AutomationScheduler | None = None


def _prune_bucket(bucket: deque[float], now: float, window_seconds: int) -> None:
    cutoff = now - window_seconds
    while bucket and bucket[0] < cutoff:
        bucket.popleft()


def _get_redis_client() -> Any:
    global _REDIS_CLIENT
    settings = get_settings()
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT
    if not settings.redis_url or redis_lib is None:
        _REDIS_CLIENT = False
        return _REDIS_CLIENT
    try:
        client = redis_lib.Redis.from_url(settings.redis_url, decode_responses=True)
        client.ping()
        _REDIS_CLIENT = client
        return _REDIS_CLIENT
    except Exception:
        _REDIS_CLIENT = False
        return _REDIS_CLIENT


def _issue_auth_tokens(db: Session, user: User) -> TokenOut:
    access_token = create_access_token(user.email)
    refresh_raw = refresh_token_raw()
    expires_at = datetime.utcnow() + timedelta(days=max(1, get_settings().auth_refresh_token_days))
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


def _record_audit_event(
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


def _webhook_secret_valid(secret_header: str | None) -> bool:
    expected = get_settings().webhook_shared_secret.strip()
    if not expected:
        return True
    return bool(secret_header and secret_header == expected)


def _register_webhook_event(
    db: Session,
    *,
    source: str,
    event_type: str,
    event_key: str,
    payload: dict[str, object],
) -> tuple[WebhookEvent, bool]:
    existing = db.scalar(select(WebhookEvent).where(WebhookEvent.event_key == event_key))
    if existing:
        return existing, True

    event = WebhookEvent(
        source=source,
        event_type=event_type,
        event_key=event_key,
        payload_json=json.dumps(payload),
        processed=1,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event, False


def _enqueue_job(
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
        available_at=available_at or datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _has_active_job(db: Session, job_type: str) -> bool:
    existing = db.scalar(
        select(JobQueue.id).where(
            JobQueue.job_type == job_type,
            JobQueue.status.in_(["queued", "processing"]),
        )
    )
    return existing is not None


def _process_queued_jobs(db: Session, limit: int = 10) -> dict[str, int]:
    now = datetime.utcnow()
    jobs = db.scalars(
        select(JobQueue)
        .where(
            JobQueue.status == "queued",
            JobQueue.available_at <= now,
        )
        .order_by(JobQueue.created_at.asc(), JobQueue.id.asc())
        .limit(max(1, limit))
    ).all()

    summary = {"picked": len(jobs), "succeeded": 0, "failed": 0, "requeued": 0}
    for job in jobs:
        job.status = "processing"
        job.updated_at = datetime.utcnow()
        db.commit()

        try:
            payload = json.loads(job.payload_json or "{}")
        except json.JSONDecodeError:
            payload = {}

        try:
            if job.job_type == "send_reminder_email":
                reminder_id = int(payload.get("reminder_id", 0))
                provider = str(payload.get("provider", "smtp"))
                reminder = db.get(ReminderEmail, reminder_id)
                if not reminder:
                    raise RuntimeError(f"Reminder not found: {reminder_id}")
                send_reminder_email(db, reminder, provider)
            elif job.job_type == "automation_cycle":
                run_automation_cycle(db)
            else:
                raise RuntimeError(f"Unsupported job type: {job.job_type}")

            job.status = "succeeded"
            job.last_error = None
            summary["succeeded"] += 1
        except Exception as exc:
            job.attempts = int(job.attempts or 0) + 1
            job.last_error = str(exc)
            if job.attempts < job.max_attempts:
                job.status = "queued"
                job.available_at = datetime.utcnow() + timedelta(seconds=20)
                summary["requeued"] += 1
            else:
                job.status = "failed"
                summary["failed"] += 1
            logger.exception("Queue job failed: id=%s type=%s", job.id, job.job_type)
        finally:
            job.updated_at = datetime.utcnow()
            db.commit()

    return summary


def _scheduler_tick() -> None:
    db = SessionLocal()
    try:
        settings = get_settings()
        if settings.automation_enabled and not _has_active_job(db, "automation_cycle"):
            _enqueue_job(
                db,
                job_type="automation_cycle",
                payload={},
                company_id=None,
                user_id=None,
                max_attempts=2,
            )
        _process_queued_jobs(db, limit=15)
    except Exception:
        logger.exception("Automation scheduler tick failed")
        raise
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _SCHEDULER
    settings = get_settings()
    _SCHEDULER = AutomationScheduler(
        interval_minutes=settings.automation_interval_minutes,
        is_enabled=lambda: get_settings().automation_enabled,
        tick=_scheduler_tick,
    )
    await _SCHEDULER.start()
    try:
        yield
    finally:
        if _SCHEDULER:
            await _SCHEDULER.stop()


app = FastAPI(title="AI Invoice Follow-up Automation API", version="1.0.0", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(invoice_router)
app.include_router(email_router)

TRACKING_GIF = base64.b64decode("R0lGODlhAQABAIABAP///wAAACwAAAAAAQABAAACAkQBADs=")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    settings = get_settings()
    if request.url.path == "/health":
        return await call_next(request)

    window_seconds = max(1, settings.rate_limit_window_seconds)
    max_requests = settings.auth_rate_limit_requests if request.url.path in _AUTH_RATE_LIMIT_PATHS else settings.rate_limit_requests
    max_requests = max(1, max_requests)
    client_ip = request.client.host if request.client else "unknown"
    key = f"{client_ip}:{request.url.path in _AUTH_RATE_LIMIT_PATHS}"

    redis_client = _get_redis_client()
    if redis_client:
        redis_key = f"rl:{key}"
        try:
            count = redis_client.incr(redis_key)
            if count == 1:
                redis_client.expire(redis_key, window_seconds)
            if count > max_requests:
                return JSONResponse(status_code=429, content={"detail": "Too many requests. Please retry later."})
        except Exception:
            redis_client = False

    if not redis_client:
        now = asyncio.get_running_loop().time()
        bucket = _RATE_LIMIT_BUCKETS[key]
        _prune_bucket(bucket, now, window_seconds)
        if len(bucket) >= max_requests:
            return JSONResponse(status_code=429, content={"detail": "Too many requests. Please retry later."})
        bucket.append(now)

    return await call_next(request)


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


def _build_late_payer_rows(invoices: list[Invoice], limit: int = 5) -> list[dict[str, object]]:
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

    rows: list[dict[str, object]] = []
    for data in groups.values():
        total = int(data["total"])
        overdue = int(data["overdue"])
        if total == 0 or overdue == 0:
            continue
        overdue_rate = round((overdue / total) * 100, 1)
        rows.append(
            {
                "customer_name": str(data["customer_name"]),
                "customer_email": str(data["customer_email"]),
                "total_invoices": total,
                "overdue_invoices": overdue,
                "overdue_rate": overdue_rate,
            }
        )

    rows.sort(key=lambda item: (float(item["overdue_rate"]), int(item["overdue_invoices"])), reverse=True)
    return rows[: max(1, limit)]


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


def _trigger_scheduler_run() -> None:
    if _SCHEDULER:
        _SCHEDULER.trigger_now()
        return
    _scheduler_tick()


@app.get("/automation/status", response_model=AutomationStatusOut)
def automation_status(_: User = Depends(require_admin)):
    if not _SCHEDULER:
        settings = get_settings()
        return AutomationStatusOut(
            enabled=settings.automation_enabled,
            running=False,
            interval_minutes=max(1, settings.automation_interval_minutes),
            last_tick_at=None,
            last_success_at=None,
            next_run_at=None,
            last_error=None,
        )
    return AutomationStatusOut(**_SCHEDULER.status())


@app.post("/automation/run-now")
def automation_run_now(background_tasks: BackgroundTasks, _: User = Depends(require_admin)):
    background_tasks.add_task(_trigger_scheduler_run)
    return {"accepted": True, "message": "Automation cycle scheduled in background"}


@app.get("/emails/track/open/{token}.gif")
def track_email_open(token: str, db: Session = Depends(get_db)):
    mark_email_opened(db, token)
    return Response(content=TRACKING_GIF, media_type="image/gif")


@app.get("/emails/track/click/{token}")
def track_email_click(token: str, target: str | None = None, db: Session = Depends(get_db)):
    reminder = mark_email_clicked(db, token)
    if not reminder:
        return RedirectResponse(url="/health", status_code=302)

    allowed_prefix = get_settings().payment_link_base_url.rstrip("/")
    target = (target or "").strip()
    if not (target.startswith("http://") or target.startswith("https://")):
        target = allowed_prefix
    elif not target.startswith(allowed_prefix):
        target = allowed_prefix

    _record_audit_event(
        db,
        action="email_link_clicked",
        entity_type="reminder_email",
        entity_id=reminder.id,
        user_id=None,
        company_id=reminder.company_id,
        details={"target": target},
    )
    return RedirectResponse(url=target, status_code=302)


@app.post("/webhooks/email/status", response_model=WebhookAckOut)
def email_status_webhook(
    payload: EmailStatusWebhookIn,
    request: Request,
    db: Session = Depends(get_db),
):
    if not _webhook_secret_valid(request.headers.get("X-Webhook-Secret")):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    event, duplicate = _register_webhook_event(
        db,
        source=payload.source,
        event_type=f"email_{payload.status}",
        event_key=payload.idempotency_key,
        payload=payload.model_dump(),
    )
    if duplicate:
        return WebhookAckOut(accepted=True, duplicate=True, event_key=event.event_key)

    reminder: ReminderEmail | None = None
    if payload.provider_message_id:
        reminder = db.scalar(
            select(ReminderEmail).where(ReminderEmail.provider_message_id == payload.provider_message_id)
        )
    if not reminder and payload.tracking_token:
        reminder = db.scalar(
            select(ReminderEmail).where(ReminderEmail.tracking_token == payload.tracking_token)
        )

    if reminder:
        if payload.status == "delivered":
            reminder.status = EmailStatus.DELIVERED
            reminder.delivered_at = datetime.utcnow()
        elif payload.status == "opened":
            reminder.status = EmailStatus.OPENED
            if reminder.opened_at is None:
                reminder.opened_at = datetime.utcnow()
        elif payload.status == "failed":
            reminder.status = EmailStatus.FAILED
            reminder.failure_reason = payload.error_message or "Provider reported failure"
        db.commit()
        db.refresh(reminder)
        _record_audit_event(
            db,
            action="email_status_webhook_applied",
            entity_type="reminder_email",
            entity_id=reminder.id,
            user_id=None,
            company_id=reminder.company_id,
            details={"status": payload.status, "source": payload.source},
        )

    return WebhookAckOut(accepted=True, duplicate=False, event_key=event.event_key)


@app.post("/webhooks/twilio/status", response_model=WebhookAckOut)
def twilio_status_webhook(payload: TwilioStatusWebhookIn, request: Request, db: Session = Depends(get_db)):
    if not _webhook_secret_valid(request.headers.get("X-Webhook-Secret")):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    sid_for_key = payload.MessageSid or "latest"
    event_key = f"twilio:{sid_for_key}:{payload.MessageStatus.lower()}"
    event, duplicate = _register_webhook_event(
        db,
        source="twilio",
        event_type=f"twilio_{payload.MessageStatus.lower()}",
        event_key=event_key,
        payload=payload.model_dump(),
    )
    if duplicate:
        return WebhookAckOut(accepted=True, duplicate=True, event_key=event.event_key)

    reminder: ReminderEmail | None = None
    if payload.MessageSid:
        reminder = db.scalar(select(ReminderEmail).where(ReminderEmail.provider_message_id == payload.MessageSid))
    if not reminder:
        reminder = db.scalar(
            select(ReminderEmail)
            .where(ReminderEmail.channel.in_(["whatsapp", "sms"]))
            .order_by(ReminderEmail.created_at.desc())
        )
    if reminder:
        normalized = payload.MessageStatus.lower()
        now = datetime.utcnow()

        if normalized in {"queued", "accepted", "sending"}:
            reminder.status = EmailStatus.SENT
            if reminder.sent_at is None:
                reminder.sent_at = now
        elif normalized in {"sent", "delivered", "read"}:
            reminder.status = EmailStatus.DELIVERED if normalized != "read" else EmailStatus.OPENED
            if reminder.sent_at is None:
                reminder.sent_at = now
            if reminder.delivered_at is None:
                reminder.delivered_at = now
            if normalized == "read" and reminder.opened_at is None:
                reminder.opened_at = now
        elif normalized in {"undelivered", "failed", "canceled"}:
            reminder.status = EmailStatus.FAILED
            reminder.failure_reason = payload.ErrorMessage or payload.ErrorCode or "Twilio reported delivery failure"

        db.commit()
        db.refresh(reminder)
        _record_audit_event(
            db,
            action="twilio_status_webhook_applied",
            entity_type="reminder_email",
            entity_id=reminder.id,
            user_id=None,
            company_id=reminder.company_id,
            details={
                "message_status": payload.MessageStatus,
                "to": payload.To,
                "from": payload.From,
            },
        )

    return WebhookAckOut(accepted=True, duplicate=False, event_key=event.event_key)




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
    _record_audit_event(
        db,
        action="company_created",
        entity_type="company",
        entity_id=company.id,
        user_id=current_user.id,
        company_id=company.id,
        details={"name": company.name},
    )
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
    _record_audit_event(
        db,
        action="company_switched",
        entity_type="company",
        entity_id=company.id,
        user_id=current_user.id,
        company_id=company.id,
        details={"company_name": company.name},
    )
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
    _record_audit_event(
        db,
        action="company_member_invited",
        entity_type="company_membership",
        user_id=current_user.id,
        company_id=active_company.id,
        details={"invited_user_id": invited_user.id, "invited_email": invited_user.email},
    )
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
    _record_audit_event(
        db,
        action="company_member_removed",
        entity_type="company_membership",
        user_id=current_user.id,
        company_id=active_company.id,
        details={"removed_user_id": target_user.id, "removed_email": target_user.email},
    )
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
    _record_audit_event(
        db,
        action="team_user_created",
        entity_type="user",
        entity_id=user.id,
        user_id=current_user.id,
        company_id=active_company.id,
        details={"email": user.email, "role": user.role.value},
    )
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
    _record_audit_event(
        db,
        action="integration_imported_invoices",
        entity_type="integration",
        user_id=current_user.id,
        company_id=active_company.id,
        details={"source": payload.source, "count": len(created)},
    )
    return created




@app.post("/payments/confirm/{token}", response_model=InvoiceOut)
def confirm_payment_by_token(token: str, payload: PaymentConfirmRequest, db: Session = Depends(get_db)):
    invoice = db.scalar(select(Invoice).where(Invoice.payment_token == token))
    if not invoice:
        raise HTTPException(status_code=404, detail="Payment token not found")

    mark_invoice_paid(db, invoice, payload.payment_reference)
    return invoice_to_out(invoice, db)


@app.post("/webhooks/payments/confirm", response_model=WebhookAckOut)
def confirm_payment_webhook(
    payload: PaymentWebhookIn,
    request: Request,
    db: Session = Depends(get_db),
):
    if not _webhook_secret_valid(request.headers.get("X-Webhook-Secret")):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    event, duplicate = _register_webhook_event(
        db,
        source=payload.source,
        event_type="payment_confirm",
        event_key=payload.idempotency_key,
        payload=payload.model_dump(),
    )
    if duplicate:
        return WebhookAckOut(accepted=True, duplicate=True, event_key=event.event_key)

    invoice: Invoice | None = None
    if payload.invoice_id:
        invoice = db.get(Invoice, payload.invoice_id)
    if not invoice and payload.payment_token:
        invoice = db.scalar(select(Invoice).where(Invoice.payment_token == payload.payment_token))
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found for webhook payment confirmation")

    was_paid = invoice.status == InvoiceStatus.PAID
    mark_invoice_paid(db, invoice, payload.payment_reference)
    if not was_paid:
        _record_audit_event(
            db,
            action="invoice_paid_via_webhook",
            entity_type="invoice",
            entity_id=invoice.id,
            user_id=None,
            company_id=invoice.company_id,
            details={"source": payload.source, "payment_reference": payload.payment_reference},
        )

    return WebhookAckOut(accepted=True, duplicate=False, event_key=event.event_key)


@app.get("/payments/pay/{token}", response_class=HTMLResponse)
def payment_checkout_page(token: str, db: Session = Depends(get_db)):
    invoice = db.scalar(select(Invoice).where(Invoice.payment_token == token))
    if not invoice:
        raise HTTPException(status_code=404, detail="Payment token not found")

    status_text = "PAID" if invoice.status == InvoiceStatus.PAID else "PENDING"
    customer_name = escape(invoice.customer_name)
    safe_status = escape(status_text)
    safe_token = escape(token)
    safe_paid_at = escape(str(invoice.paid_at)) if invoice.paid_at else ""
    safe_payment_reference = escape(invoice.payment_reference or "")
    paid_notice = (
        f"<p><strong>Paid at:</strong> {safe_paid_at}</p><p><strong>Reference:</strong> {safe_payment_reference}</p>"
        if invoice.status == InvoiceStatus.PAID
        else ""
    )

    return f"""
    <html>
      <head><title>Invoice Payment</title></head>
      <body style='font-family: Arial, sans-serif; max-width: 680px; margin: 24px auto; padding: 16px;'>
        <h2>Invoice #{invoice.id} Payment</h2>
        <p><strong>Customer:</strong> {customer_name}</p>
        <p><strong>Amount:</strong> ${invoice.amount:,.2f}</p>
        <p><strong>Status:</strong> {safe_status}</p>
        {paid_notice}
        <form method='post' action='/payments/confirm-form/{safe_token}'>
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

    if invoice.status == InvoiceStatus.PAID:
        paid_reference = escape(invoice.payment_reference or "")
        return (
            "<html><body style='font-family: Arial, sans-serif; max-width:680px; margin: 24px auto;'>"
            "<h3>Payment was already recorded.</h3>"
            f"<p>Invoice #{invoice.id} remains paid with reference <strong>{paid_reference}</strong>.</p>"
            "</body></html>"
        )

    mark_invoice_paid(db, invoice, payment_reference)
    safe_reference = escape(invoice.payment_reference or "")
    return (
        "<html><body style='font-family: Arial, sans-serif; max-width:680px; margin: 24px auto;'>"
        "<h3>Payment recorded successfully.</h3>"
        f"<p>Invoice #{invoice.id} is now marked as paid with reference <strong>{safe_reference}</strong>.</p>"
        "</body></html>"
    )




@app.get("/audit/logs", response_model=list[AuditLogOut])
def list_audit_logs(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    active_company = get_active_company(db, current_user)
    safe_limit = min(200, max(1, limit))
    logs = db.scalars(
        select(AuditLog)
        .where(AuditLog.company_id == active_company.id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(safe_limit)
    ).all()

    out: list[AuditLogOut] = []
    for log in logs:
        try:
            details = json.loads(log.details_json) if log.details_json else {}
        except json.JSONDecodeError:
            details = {}
        out.append(
            AuditLogOut(
                id=log.id,
                company_id=log.company_id,
                user_id=log.user_id,
                action=log.action,
                entity_type=log.entity_type,
                entity_id=log.entity_id,
                details=details,
                created_at=log.created_at,
            )
    )
    return out


@app.get("/jobs/queue", response_model=list[JobQueueOut])
def list_queue_jobs(
    limit: int = 100,
    status: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    active_company = get_active_company(db, current_user)
    safe_limit = min(500, max(1, limit))
    query = select(JobQueue).where(
        (JobQueue.company_id == active_company.id) | (JobQueue.company_id.is_(None))
    )
    if status:
        query = query.where(JobQueue.status == status)
    jobs = db.scalars(
        query.order_by(JobQueue.created_at.desc(), JobQueue.id.desc()).limit(safe_limit)
    ).all()

    out: list[JobQueueOut] = []
    for job in jobs:
        try:
            payload = json.loads(job.payload_json or "{}")
        except json.JSONDecodeError:
            payload = {}
        out.append(
            JobQueueOut(
                id=job.id,
                company_id=job.company_id,
                user_id=job.user_id,
                job_type=job.job_type,
                payload=payload,
                status=job.status,
                attempts=job.attempts,
                max_attempts=job.max_attempts,
                available_at=job.available_at,
                last_error=job.last_error,
                created_at=job.created_at,
                updated_at=job.updated_at,
            )
        )
    return out


@app.get("/jobs/stats", response_model=QueueStatsOut)
def queue_stats(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    active_company = get_active_company(db, current_user)
    company_scope = (JobQueue.company_id == active_company.id) | (JobQueue.company_id.is_(None))
    queued = db.scalar(select(func.count()).select_from(JobQueue).where(company_scope, JobQueue.status == "queued")) or 0
    processing = db.scalar(select(func.count()).select_from(JobQueue).where(company_scope, JobQueue.status == "processing")) or 0
    succeeded = db.scalar(select(func.count()).select_from(JobQueue).where(company_scope, JobQueue.status == "succeeded")) or 0
    failed = db.scalar(select(func.count()).select_from(JobQueue).where(company_scope, JobQueue.status == "failed")) or 0
    return QueueStatsOut(queued=queued, processing=processing, succeeded=succeeded, failed=failed)


@app.post("/jobs/run-now")
def run_queue_now(
    limit: int = 25,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    get_active_company(db, current_user)
    summary = _process_queued_jobs(db, limit=min(100, max(1, limit)))
    return summary


@app.get("/ops/metrics", response_model=OpsMetricsOut)
def ops_metrics(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    active_company = get_active_company(db, current_user)
    now = datetime.utcnow()
    lookback = now - timedelta(hours=24)

    total_invoices = db.scalar(
        select(func.count()).select_from(Invoice).where(Invoice.company_id == active_company.id)
    ) or 0
    overdue_invoices = db.scalar(
        select(func.count())
        .select_from(Invoice)
        .where(
            Invoice.company_id == active_company.id,
            Invoice.status == InvoiceStatus.PENDING,
            Invoice.due_date < now.date(),
        )
    ) or 0
    queued_jobs = db.scalar(
        select(func.count())
        .select_from(JobQueue)
        .where(
            ((JobQueue.company_id == active_company.id) | (JobQueue.company_id.is_(None))),
            JobQueue.status == "queued",
        )
    ) or 0
    failed_jobs = db.scalar(
        select(func.count())
        .select_from(JobQueue)
        .where(
            ((JobQueue.company_id == active_company.id) | (JobQueue.company_id.is_(None))),
            JobQueue.status == "failed",
        )
    ) or 0
    failed_emails = db.scalar(
        select(func.count())
        .select_from(ReminderEmail)
        .where(
            ReminderEmail.company_id == active_company.id,
            ReminderEmail.status == EmailStatus.FAILED,
        )
    ) or 0
    webhook_events_24h = db.scalar(
        select(func.count())
        .select_from(WebhookEvent)
        .where(WebhookEvent.created_at >= lookback)
    ) or 0

    return OpsMetricsOut(
        total_invoices=total_invoices,
        overdue_invoices=overdue_invoices,
        queued_jobs=queued_jobs,
        failed_jobs=failed_jobs,
        failed_emails=failed_emails,
        webhook_events_24h=webhook_events_24h,
    )


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
    rows = _build_late_payer_rows(invoices, limit=5)
    insights: list[LatePayerInsight] = []
    for data in rows:
        overdue_rate = float(data["overdue_rate"])
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
                total_invoices=int(data["total_invoices"]),
                overdue_invoices=int(data["overdue_invoices"]),
                overdue_rate=overdue_rate,
                risk_level=risk_level,
                insight=insight,
            )
        )
    return insights


@app.get("/reports/overview", response_model=ReportsOverviewOut)
def reports_overview(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    active_company = get_active_company(db, current_user)
    invoices = db.scalars(
        select(Invoice)
        .where(Invoice.company_id == active_company.id)
        .order_by(Invoice.due_date.asc())
    ).all()

    if not invoices:
        return ReportsOverviewOut(
            monthly_recovery=[],
            monthly_recovery_rate=0.0,
            avg_payment_delay_days=0.0,
            email_open_rate=0.0,
            email_click_rate=0.0,
            top_late_payers=[],
        )

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
    monthly_recovery = []
    total_invoiced = 0.0
    total_paid = 0.0
    for month in month_keys:
        bucket = monthly_agg[month]
        invoiced_amount = round(bucket["invoiced"], 2)
        paid_amount = round(bucket["paid"], 2)
        rate = round((paid_amount / invoiced_amount) * 100, 1) if invoiced_amount > 0 else 0.0
        monthly_recovery.append(
            {
                "month": _month_label(month),
                "invoiced_amount": invoiced_amount,
                "paid_amount": paid_amount,
                "recovery_rate": rate,
            }
        )
        total_invoiced += invoiced_amount
        total_paid += paid_amount

    monthly_recovery_rate = round((total_paid / total_invoiced) * 100, 1) if total_invoiced > 0 else 0.0
    avg_payment_delay_days = round(sum(paid_delay_days) / len(paid_delay_days), 1) if paid_delay_days else 0.0

    reminder_emails = db.scalars(
        select(ReminderEmail).where(ReminderEmail.company_id == active_company.id)
    ).all()
    sent_like_count = sum(1 for item in reminder_emails if item.sent_at is not None)
    opened_count = sum(1 for item in reminder_emails if item.opened_at is not None)
    clicked_count = sum(1 for item in reminder_emails if int(item.click_count or 0) > 0)
    email_open_rate = round((opened_count / sent_like_count) * 100, 1) if sent_like_count else 0.0
    email_click_rate = round((clicked_count / sent_like_count) * 100, 1) if sent_like_count else 0.0

    late_rows = _build_late_payer_rows(invoices, limit=5)
    return ReportsOverviewOut(
        monthly_recovery=monthly_recovery,
        monthly_recovery_rate=monthly_recovery_rate,
        avg_payment_delay_days=avg_payment_delay_days,
        email_open_rate=email_open_rate,
        email_click_rate=email_click_rate,
        top_late_payers=[TopLatePayerOut(**row) for row in late_rows],
    )


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
