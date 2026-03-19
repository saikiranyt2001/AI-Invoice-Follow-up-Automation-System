from __future__ import annotations

import argparse
import secrets
import sys
from datetime import date, timedelta

import httpx


def fail(message: str) -> None:
    print(f"FAIL {message}")
    raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backend API smoke test")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base URL")
    parser.add_argument(
        "--email",
        default="",
        help="Existing admin/accountant email to use instead of creating a new user",
    )
    parser.add_argument("--password", default="StrongPass123!", help="Password for test user")
    return parser.parse_args()


def post_json(client: httpx.Client, path: str, payload: dict, headers: dict | None = None) -> dict:
    response = client.post(path, json=payload, headers=headers)
    if response.status_code >= 400:
        fail(f"{path} returned {response.status_code}: {response.text}")
    return response.json()


def get_json(client: httpx.Client, path: str, headers: dict | None = None):
    response = client.get(path, headers=headers)
    if response.status_code >= 400:
        fail(f"{path} returned {response.status_code}: {response.text}")
    return response.json()


def main() -> int:
    args = parse_args()

    email = args.email.strip().lower()
    username = ""
    created_role = ""
    if not email:
        suffix = secrets.token_hex(4)
        email = f"smoke_{suffix}@example.com"
        username = f"smoke_{suffix}"

    with httpx.Client(base_url=args.base_url, timeout=20.0) as client:
        health = get_json(client, "/health")
        if health.get("status") != "ok":
            fail("/health did not return status=ok")
        print("PASS health")

        if username:
            signup = post_json(
                client,
                "/auth/signup",
                {"username": username, "email": email, "password": args.password},
            )
            token = signup.get("access_token")
            if not token:
                fail("signup response missing access_token")
            created_role = str(signup.get("user", {}).get("role", "")).lower()
            print(f"PASS signup role={created_role or 'unknown'}")
        else:
            print(f"PASS using_existing_user email={email}")

        login = post_json(client, "/auth/login", {"email": email, "password": args.password})
        token = login.get("access_token")
        if not token:
            fail("login response missing access_token")
        current_role = str(login.get("user", {}).get("role", created_role)).lower()
        print(f"PASS login role={current_role or 'unknown'}")

        if current_role not in {"admin", "accountant"}:
            fail(
                "authenticated user does not have write access required for smoke flows; "
                "use a fresh database for first-user signup or pass --email for an existing admin/accountant account"
            )

        auth = {"Authorization": f"Bearer {token}"}

        invoice = post_json(
            client,
            "/invoices",
            {
                "customer_name": "Smoke Customer",
                "customer_email": "ar.smoke@example.com",
                "amount": 500.0,
                "due_date": (date.today() - timedelta(days=3)).isoformat(),
            },
            headers=auth,
        )
        invoice_id = invoice.get("id")
        if not invoice_id:
            fail("create invoice missing id")
        print("PASS create_invoice")

        overdue = get_json(client, "/overdue", headers=auth)
        if not any(item.get("id") == invoice_id for item in overdue):
            fail("overdue list does not include created overdue invoice")
        print("PASS overdue_detection")

        draft = post_json(
            client,
            "/generate-email",
            {"invoice_id": invoice_id, "tone": "professional"},
            headers=auth,
        )
        email_id = draft.get("id")
        if not email_id:
            fail("generate email missing id")
        print("PASS generate_email")

        pending = get_json(client, "/emails/pending-approvals", headers=auth)
        if not any(item.get("id") == email_id for item in pending):
            fail("pending approvals does not include generated email")
        print("PASS pending_approval_queue")

        approved = post_json(
            client,
            f"/emails/{email_id}/approve",
            {"provider": "smtp"},
            headers=auth,
        )
        if approved.get("status") not in {"sent", "delivered", "opened", "failed", "approved"}:
            fail("approve/send returned unexpected status")
        print(f"PASS approve_send status={approved.get('status')}")

        history = get_json(client, "/emails", headers=auth)
        if not any(item.get("id") == email_id for item in history):
            fail("email history missing approved email")
        print("PASS email_history")

    print("SMOKE_TEST_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
