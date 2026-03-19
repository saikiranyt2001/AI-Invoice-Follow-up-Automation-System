from __future__ import annotations

from datetime import date
from io import BytesIO

from openpyxl import Workbook

from .conftest import signup


def test_invoice_upload_accepts_excel_file(client):
    token, _ = signup(client, "admin_import", "admin_import@example.com")
    auth = {"Authorization": f"Bearer {token}"}

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["customer_name", "customer_email", "amount", "due_date", "customer_phone"])
    sheet.append(
        [
            "Excel Customer",
            "excel.customer@example.com",
            275.5,
            date.today().isoformat(),
            "+15550001111",
        ]
    )

    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)

    response = client.post(
        "/invoices/upload",
        headers=auth,
        files={
            "file": (
                "invoices.xlsx",
                stream.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created_count"] == 1
    assert body["error_count"] == 0
    assert body["invoices"][0]["customer_email"] == "excel.customer@example.com"


def test_integrations_include_tally_source_and_import(client):
    token, _ = signup(client, "admin_tally", "admin_tally@example.com")
    auth = {"Authorization": f"Bearer {token}"}

    sources = client.get("/integrations/sources", headers=auth)
    assert sources.status_code == 200, sources.text
    ids = {item["id"] for item in sources.json().get("sources", [])}
    assert "tally" in ids

    imported = client.post(
        "/integrations/import-invoices",
        headers=auth,
        json={"source": "tally", "count": 2},
    )
    assert imported.status_code == 200, imported.text
    assert len(imported.json()) == 2
