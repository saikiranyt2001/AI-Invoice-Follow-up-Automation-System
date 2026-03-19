from __future__ import annotations

from datetime import datetime

from app.models import Invoice
from app.time_utils import utcnow


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_invoice_pdf(invoice: Invoice, payment_url: str, company_name: str) -> bytes:
    lines = [
        f"Invoice #{invoice.id}",
        f"Generated: {utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
        "",
        f"Company: {company_name}",
        f"Customer: {invoice.customer_name}",
        f"Customer Email: {invoice.customer_email}",
        f"Amount Due: ${invoice.amount:,.2f}",
        f"Due Date: {invoice.due_date.isoformat()}",
        f"Status: {invoice.status.value}",
    ]

    if invoice.payment_reference:
        lines.append(f"Payment Reference: {invoice.payment_reference}")
    if invoice.paid_at:
        lines.append(f"Paid At: {invoice.paid_at.isoformat()}")

    lines.extend(["", "Payment Link:", payment_url])

    text_stream = ["BT", "/F1 12 Tf", "50 790 Td", "14 TL"]
    for idx, line in enumerate(lines):
        escaped = _pdf_escape(line)
        if idx == 0:
            text_stream.append(f"({escaped}) Tj")
        else:
            text_stream.append(f"T* ({escaped}) Tj")
    text_stream.append("ET")

    stream_data = "\n".join(text_stream).encode("latin-1", errors="replace")

    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Length " + str(len(stream_data)).encode("ascii") + b" >>\nstream\n" + stream_data + b"\nendstream\nendobj\n",
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)

    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))

    trailer = (
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
        f"startxref\n{xref_start}\n%%EOF\n"
    )
    pdf.extend(trailer.encode("ascii"))
    return bytes(pdf)
