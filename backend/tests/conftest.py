from __future__ import annotations

import importlib
import sys

import pytest
from fastapi.testclient import TestClient

APP_MODULES = [
    "app.api",
    "app.api.support",
    "app.api.routes",
    "app.api.routes.auth",
    "app.api.routes.emails",
    "app.api.routes.invoices",
    "app.email",
    "app.email.sender",
    "app.main",
    "app.security",
    "app.services",
    "app.services.ai_service",
    "app.services.analytics_service",
    "app.services.email_service",
    "app.services.invoice_service",
    "app.services.scheduler_service",
    "app.models",
    "app.database",
    "app.config",
]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("AUTH_SECRET_KEY", "test-secret-key-32-bytes-minimum!!")
    monkeypatch.setenv("AUTH_RATE_LIMIT_REQUESTS", "3")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")
    monkeypatch.setenv("DRY_RUN_EMAIL", "true")
    monkeypatch.setenv("SMS_ENABLED", "true")
    monkeypatch.setenv("SMS_DRY_RUN", "true")

    for module_name in APP_MODULES:
        sys.modules.pop(module_name, None)

    main = importlib.import_module("app.main")
    with TestClient(main.app) as test_client:
        yield test_client


def signup(client: TestClient, username: str, email: str, password: str = "StrongPass123!"):
    response = client.post(
        "/auth/signup",
        json={"username": username, "email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    return payload["access_token"], payload["user"]
