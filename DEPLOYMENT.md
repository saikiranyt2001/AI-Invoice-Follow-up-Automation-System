# Deployment Guide

## Production Baseline

- Use PostgreSQL, not SQLite.
- Use a strong `AUTH_SECRET_KEY` with at least 32 bytes.
- Set `CORS_ALLOWED_ORIGINS` to your real frontend origin, not `*`.
- Disable dry-run flags in production.
- Put TLS in front of the app before exposing it publicly.

## Docker Deployment

1. Copy the production env template:

```bash
copy .env.production.example .env
```

2. Fill in the required values in `.env`:

- `POSTGRES_PASSWORD`
- `AUTH_SECRET_KEY`
- `CORS_ALLOWED_ORIGINS`
- `VITE_API_BASE`
- your email/payment/Twilio provider settings

3. Start the stack:

```bash
docker compose --env-file .env -f docker-compose.prod.yml up --build -d
```

4. Verify:

- Frontend: `http://localhost:8080`
- Backend health: `http://localhost:8000/health`

## Recommended Production Setup

- Frontend origin:
  `https://app.example.com`
- Backend/API origin:
  `https://api.example.com`
- Reverse proxy:
  Nginx, Caddy, Traefik, or a cloud load balancer
- Database:
  managed PostgreSQL where possible
- Secrets:
  inject through deployment platform secrets, not committed files

## Pre-Go-Live Checklist

- `DRY_RUN_EMAIL=false`
- `SMS_DRY_RUN=false`
- `DATABASE_URL` points to PostgreSQL
- `AUTH_SECRET_KEY` rotated to a strong secret
- `CORS_ALLOWED_ORIGINS` limited to the real frontend origin
- payment link base URLs point to production domains
- webhook secrets configured
- SMTP/SendGrid/Twilio tested in staging
- backups enabled for PostgreSQL
- HTTPS enabled at the edge

## Notes

- The frontend image is static Nginx hosting for the built Vite app.
- The backend image runs Uvicorn and expects environment-driven configuration.
- The compose file is a practical baseline, not a full platform substitute.
