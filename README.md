# AI Invoice Follow-up Automation System

AI-powered receivables automation platform for tracking unpaid invoices, sending follow-ups, and improving collection outcomes.

## 1. Problem

Businesses lose money due to unpaid invoices.

Late payments create cash-flow pressure, increase manual finance work, and force teams to spend time chasing customers instead of running operations. Many businesses still rely on manual reminders, spreadsheets, and inconsistent follow-up processes, which leads to missed collections and poor visibility.

## 2. Solution

Automated AI-powered follow-ups.

This system helps finance and operations teams upload invoices, track payment status, generate reminder messages, schedule automated follow-ups, and monitor outcomes from a single dashboard. It combines workflow automation, role-based access, audit visibility, and AI-generated payment reminders.

## 3. Features

- JWT-based authentication with refresh-token support
- Role-based users: `Admin`, `Accountant`, `Viewer`
- Multi-company workspace support
- Invoice creation and tracking
- CSV invoice upload
- Excel invoice upload (`.xlsx`)
- Automatic invoice parsing and validation
- Overdue invoice detection
- Payment links via internal checkout, Stripe link mode, or Razorpay link mode
- Payment confirmation flow
- AI-powered message generation
- Smart tone recommendation with rationale (delay, amount, payment history)
- Message styles such as `Friendly Reminder` and `Urgent Payment Notice`
- Email delivery via SMTP
- Gmail API email sending
- Twilio SMS and Twilio WhatsApp reminder support with multi-channel follow-up sequencing
- Follow-up scheduling for Day 1, Day 5, and Day 10
- Background automation scheduler
- Reminder approval workflow
- Email status tracking: draft, approved, sent, delivered, opened, failed
- Email engagement tracking: open and click analytics
- Delivery feedback tracking: bounce and spam complaint analytics
- Invoice PDF generation and secure download endpoint
- Retry handling for failed reminders
- Dashboard with invoice and follow-up KPIs
- Reports analytics view: monthly recovery, delay, monthly cashflow, open/click/bounce/spam rates, top late payers
- Follow-up pipeline visibility
- Audit logs for invoice, email, and user actions
- Queue and operations monitoring
- Payment webhook reconciliation
- Email webhook reconciliation
- SMS-ready reminder path
- Integration-ready import scaffolding (QuickBooks, Zoho Books, Tally, and more)

## 4. Demo Flow

Upload -> Track -> Auto follow-up -> Payment

### Step 1: Upload

Upload invoices using:

- manual entry
- CSV file
- Excel file

The system validates and parses invoice data automatically.

### Step 2: Track

The dashboard shows:

- total invoices
- paid vs pending
- overdue invoices
- follow-up status

### Step 3: Auto Follow-up

For overdue invoices, the platform:

- generates AI-powered reminder messages
- applies reminder cadence on Day 1, Day 5, and Day 10
- sends reminders through SMTP or Gmail API
- records email delivery and engagement events

### Step 4: Payment

Customers can pay through the generated payment flow, and the system updates invoice status, payment reference, and audit history automatically.

## 5. Tech Stack

- Backend: FastAPI
- Frontend: React + Vite
- Database: SQLite by default, PostgreSQL-ready
- ORM: SQLAlchemy
- Auth: JWT
- Scheduler: FastAPI background scheduler
- Queue/Cache support: Redis-ready
- AI generation: OpenAI API
- Email: SMTP / Gmail API

## Product Modules

### Email Automation Engine

- SMTP sending
- Gmail API sending
- AI-generated templates
- automated reminder cadence

### Dashboard

- invoice health summary
- overdue tracking
- follow-up pipeline visibility
- ops and audit monitoring

### Scheduler

- automated background reminder execution
- manual trigger endpoint
- scheduler status endpoint
- configurable reminder day thresholds through environment settings

### Authentication

- secure login
- JWT access tokens
- refresh tokens
- role-based access
- MFA support

### Invoice Import

- CSV parsing
- Excel parsing
- import validation
- structured import results

### Auditability

- invoice creation and payment events
- reminder lifecycle events
- user and admin actions

## Run Locally

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Backend URL: `http://127.0.0.1:8000`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend URL: `http://127.0.0.1:5173`

Set `VITE_API_BASE` if the frontend should point at a non-default backend URL.

## Local Stack Helpers

Run both services together with a clean local SQLite database:

```bash
python scripts/run_local_stack.py
```

Validate a clean local stack end to end:

```bash
python scripts/validate_local_stack.py
```

Run backend tests, backend lint/format checks, and frontend checks:

```bash
python scripts/check_project.py
```

## Production Deployment

Production deployment assets are included:

- [docker-compose.prod.yml](/C:/Users/saiki/OneDrive/Documents/AI%20Invoice%20Follow-up%20Automation%20System/docker-compose.prod.yml)
- [DEPLOYMENT.md](/C:/Users/saiki/OneDrive/Documents/AI%20Invoice%20Follow-up%20Automation%20System/DEPLOYMENT.md)
- [backend/Dockerfile](/C:/Users/saiki/OneDrive/Documents/AI%20Invoice%20Follow-up%20Automation%20System/backend/Dockerfile)
- [frontend/Dockerfile](/C:/Users/saiki/OneDrive/Documents/AI%20Invoice%20Follow-up%20Automation%20System/frontend/Dockerfile)

Start from [.env.production.example](/C:/Users/saiki/OneDrive/Documents/AI%20Invoice%20Follow-up%20Automation%20System/.env.production.example) and follow [DEPLOYMENT.md](/C:/Users/saiki/OneDrive/Documents/AI%20Invoice%20Follow-up%20Automation%20System/DEPLOYMENT.md).

## Demo Credentials Flow

- Sign up the first user
- First user becomes `admin`
- Upload invoices
- Generate or approve reminders
- Run automated follow-ups
- Track reminder outcomes
- Confirm payment

## Useful Endpoints

- `POST /auth/signup`
- `POST /auth/login`
- `GET /dashboard/stats`
- `POST /invoices`
- `POST /invoices/upload`
- `GET /invoices`
- `GET /overdue`
- `POST /generate-email`
- `GET /reports/overview`
- `GET /emails/analytics`
- `GET /emails`
- `GET /emails/pending-approvals`
- `GET /emails/track/open/{token}.gif`
- `GET /emails/track/click/{token}`
- `POST /webhooks/twilio/status`
- `POST /webhooks/email/status`
- `GET /invoices/{invoice_id}/pdf`
- `POST /automation/run-now`
- `GET /automation/status`
- `GET /audit/logs`

## Environment Configuration Highlights

- `AUTO_REMINDER_DAY_FRIENDLY`: default `1`
- `AUTO_REMINDER_DAY_PROFESSIONAL`: default `5`
- `AUTO_REMINDER_DAY_STRICT`: default `10`
- `TRACKING_BASE_URL`: base URL for open/click tracking links
- `PAYMENT_PROVIDER`: `internal`, `stripe`, or `razorpay`
- `STRIPE_PAYMENT_LINK_BASE_URL`: Stripe payment link base URL for Pay Now links
- `RAZORPAY_PAYMENT_LINK_BASE_URL`: Razorpay payment link base URL for Pay Now links
- `AUTO_FOLLOWUP_CHANNELS`: comma-separated channel order (for example `smtp,twilio_whatsapp,twilio_sms`)
- `TWILIO_ACCOUNT_SID`: Twilio account SID
- `TWILIO_AUTH_TOKEN`: Twilio auth token
- `TWILIO_FROM_NUMBER`: Twilio SMS sender number
- `TWILIO_WHATSAPP_FROM_NUMBER`: Twilio WhatsApp sender (for example `whatsapp:+14155238886`)
- `AUTH_SECRET_KEY`: use a random secret with at least 32 bytes for HS256
- `SMS_ENABLED`: enable SMS/WhatsApp sending path
- `SMS_DRY_RUN`: dry-run mode for Twilio channel testing

## Notes

- SQLite works out of the box for demos.
- PostgreSQL can be used in production by changing `DATABASE_URL`.
- Real AI generation requires `OPENAI_API_KEY`.
- Real email sending requires SMTP or Gmail API configuration.
- Stripe/Razorpay payment links require the matching payment link base URL environment variables.
- Frontend API base can be overridden with `VITE_API_BASE`.
