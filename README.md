# AI Invoice Follow-up Automation System

This project includes:

- `backend`: FastAPI API for invoices, overdue detection, AI reminder generation, approval workflow, and email sending.
- `frontend`: React dashboard for operations and monitoring.

## MVP Features Implemented

- Overdue invoice detection
- AI-style payment reminder generation with tone selection (Friendly / Professional / Strict)
- Pending approval workflow (Preview, Edit, Approve+Send, Reject)
- Email sending system (SMTP + simulated Gmail API path)
- Automated overdue reminder scheduler
- Staged automation cadence (Day 1 Friendly, Day 7 Professional, Day 14 Strict)
- Email lifecycle tracking (Sent / Delivered / Opened)
- Failed email retry loop with configurable delay/retry limits
- Payment links embedded in reminder emails
- Invoice payment confirmation and paid-status tracking
- Dashboard with cards, invoices table, approval queue
- Authentication (Signup/Login + JWT protected APIs + user-scoped data)

## Bonus Features Included

- CSV invoice upload
- Real-time dashboard refresh (polling every 15 seconds)
- Email history page
- AI insights for frequent late payers
- Customer payment behavior history with rolling risk trend
- Multi-user system (Admin + Team)
- Extended role support (Admin, Manager, Accountant, Team)
- Multi-company workspace with active-company switching and scoped data views
- Company-level team collaboration (users assigned to the same company share invoices/reminders/insights)
- Integration-ready invoice import (fake_api, xero, quickbooks, zoho_books simulation)
- OAuth-style connector scaffold for Xero, QuickBooks, and Zoho Books (connect, callback, sync, disconnect)

QuickBooks can run in live OAuth mode when `QUICKBOOKS_CLIENT_ID` and `QUICKBOOKS_CLIENT_SECRET` are configured; otherwise it falls back to demo scaffold mode.

## 1) Run Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Backend URL: `http://127.0.0.1:8000`

Notes:
- By default, `DRY_RUN_EMAIL=true`, so email send requests are marked sent without contacting SMTP.
- Set `DRY_RUN_EMAIL=false` and configure SMTP values to send real emails.
- `DATABASE_URL` defaults to SQLite and is PostgreSQL-ready (set e.g. `postgresql+psycopg://...`).
- Scheduler runs automatically when `AUTOMATION_ENABLED=true`.
- Use `AUTO_SEND_WITHOUT_APPROVAL=true` only if your company policy allows bypassing manual approval.
- Set `PAYMENT_LINK_BASE_URL` to your real Stripe/Razorpay hosted payment page base URL.
	Default is local demo endpoint: `/payments/pay/{token}`.

### Optional: Enable Real AI Email Generation

Set these variables in `backend/.env`:

```bash
OPENAI_API_KEY=your_api_key
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=https://api.openai.com/v1
```

Behavior:
- If `OPENAI_API_KEY` is configured, reminder content is generated using the model.
- If AI call fails or is not configured, the system automatically falls back to built-in templates.

### Authentication

All business endpoints are protected and require a Bearer token.

Auth endpoints:
- `POST /auth/signup`
- `POST /auth/login`
- `GET /auth/me`

Role behavior:
- If no admin exists, the next signup becomes `admin` automatically.
- Later signups default to `team`.
- Admin can manage users from Team tab/API and assign `manager` and `accountant` roles.

Use the frontend login/signup screen to authenticate, or call APIs directly and send:

```bash
Authorization: Bearer <access_token>
```

## 2) Run Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend URL: `http://127.0.0.1:5173`

If backend is not on default URL, set:

```bash
set VITE_API_BASE=http://127.0.0.1:8000
```

## 3) Smoke Checks

Backend API smoke test (run backend first on port 8000):

```bash
cd backend
"..\\.venv\\Scripts\\python.exe" smoke_test.py --base-url http://127.0.0.1:8000
```

Frontend build + audit:

```bash
cd frontend
npm run check
npm run audit
```

## 4) CI Automation

GitHub Actions workflow is configured at `.github/workflows/ci.yml` and runs on push/pull request:

- Backend smoke test (`backend/smoke_test.py`)
- Frontend build check (`npm run check`)
- Frontend dependency audit (`npm run audit`)

## API Endpoints

- `POST /invoices`
- `POST /invoices/{invoice_id}/mark-paid`
- `POST /invoices/upload-csv`
- `GET /invoices`
- `GET /overdue`
- `POST /auth/signup`
- `POST /auth/login`
- `GET /auth/me`
- `GET /companies`
- `POST /companies`
- `POST /companies/switch`
- `POST /companies/active/invite` (admin)
- `POST /companies/active/remove-member` (admin)
- `POST /automation/run-now` (admin)
- `POST /generate-email`
- `GET /team/users` (admin)
- `POST /team/users` (admin)
- `GET /integrations/sources`
- `GET /integrations/connectors`
- `POST /integrations/{provider}/oauth/start`
- `POST /integrations/{provider}/oauth/callback`
- `POST /integrations/{provider}/sync-invoices`
- `POST /integrations/{provider}/disconnect`
- `POST /integrations/import-invoices`
- `GET /emails/pending-approvals`
- `PATCH /emails/{email_id}/edit`
- `POST /emails/{email_id}/approve`
- `POST /emails/{email_id}/reject`
- `POST /emails/{email_id}/send`
- `GET /payments/pay/{token}`
- `POST /payments/confirm/{token}`
- `GET /emails`
- `GET /dashboard/stats`
- `GET /insights/late-payers`
- `GET /customers/history`
