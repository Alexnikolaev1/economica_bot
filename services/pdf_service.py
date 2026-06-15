"""Обёртка генерации PDF-счёта."""

from __future__ import annotations

import logging
from datetime import date

from templates.invoice_template import generate_invoice_pdf

logger = logging.getLogger(__name__)


async def create_invoice_pdf(
    user: dict,
    client_name: str,
    service_description: str,
    amount: float,
    invoice_number: int,
    invoice_date: date | None = None,
) -> tuple[bytes, str]:
    if invoice_date is None:
        invoice_date = date.today()

    pdf_bytes = generate_invoice_pdf(
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        user_full_name=user.get("full_name", ""),
        user_inn=user.get("inn", ""),
        user_bank_account=user.get("bank_account", ""),
        client_name=client_name,
        service_description=service_description,
        amount=amount,
    )
    filename = f"invoice_{invoice_number}_{invoice_date.strftime('%Y%m%d')}.pdf"
    return pdf_bytes, filename
