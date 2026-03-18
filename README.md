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
- Role-based users: `Admin`, `Accountant`, plus extended internal roles
- Multi-company workspace support
- Invoice creation and tracking
- CSV invoice upload
- Excel invoice upload (`.xlsx`)
- Automatic invoice parsing and validation
- Overdue invoice detection
- Payment link generation
- Payment confirmation flow
- AI-powered message generation
- Message styles such as `Friendly Reminder` and `Urgent Payment Notice`
- Email delivery via SMTP
- Gmail API email sending
- Follow-up scheduling for Day 3, Day 7, and Day 14
- Background automation scheduler
- Reminder approval workflow
- Email status tracking: draft, approved, sent, delivered, opened, failed
- Retry handling for failed reminders
- Dashboard with invoice and follow-up KPIs
- Follow-up pipeline visibility
- Audit logs for invoice, email, and user actions
- Queue and operations monitoring
- Payment webhook reconciliation
- Email webhook reconciliation
- SMS-ready reminder path
- Integration-ready import scaffolding

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
- applies reminder cadence on Day 3, Day 7, and Day 14
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
- `GET /emails`
- `GET /emails/pending-approvals`
- `POST /automation/run-now`
- `GET /automation/status`
- `GET /audit/logs`

## Notes

- SQLite works out of the box for demos.
- PostgreSQL can be used in production by changing `DATABASE_URL`.
- Real AI generation requires `OPENAI_API_KEY`.
- Real email sending requires SMTP or Gmail API configuration.
