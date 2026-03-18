# AI Invoice Follow-up Automation System

This project includes:

- `backend`: FastAPI API for invoices, overdue detection, AI reminder generation, approval workflow, and email sending.
- `frontend`: React dashboard for operations and monitoring.

## MVP Features Implemented

- Overdue invoice detection
- AI-style payment reminder generation with tone selection (Friendly / Professional / Strict)
- Pending approval workflow (Preview, Edit, Approve+Send, Reject)
- Email sending system (SMTP + simulated Gmail API path)
- Dashboard with cards, invoices table, approval queue
- Authentication (Signup/Login + JWT protected APIs + user-scoped data)

## Bonus Features Included

- CSV invoice upload
- Real-time dashboard refresh (polling every 15 seconds)
- Email history page
- AI insights for frequent late payers
- Multi-user system (Admin + Team)
- Integration-ready invoice import (fake_api, xero, quickbooks simulation)

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
- Admin can manage users from Team tab/API.

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

## API Endpoints

- `POST /invoices`
- `POST /invoices/upload-csv`
- `GET /invoices`
- `GET /overdue`
- `POST /auth/signup`
- `POST /auth/login`
- `GET /auth/me`
- `POST /generate-email`
- `GET /team/users` (admin)
- `POST /team/users` (admin)
- `GET /integrations/sources`
- `POST /integrations/import-invoices`
- `GET /emails/pending-approvals`
- `PATCH /emails/{email_id}/edit`
- `POST /emails/{email_id}/approve`
- `POST /emails/{email_id}/reject`
- `POST /emails/{email_id}/send`
- `GET /emails`
- `GET /dashboard/stats`
- `GET /insights/late-payers`
