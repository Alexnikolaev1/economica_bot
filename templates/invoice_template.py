"""
templates/invoice_template.py — PDF-счёт на оплату.
"""

from __future__ import annotations

import io
import logging
import os
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

logger = logging.getLogger(__name__)

FONT_NAME = "Helvetica"
FONT_BOLD = "Helvetica-Bold"

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _try_register_dejavu() -> bool:
    paths = [
        _PROJECT_ROOT / "assets" / "fonts" / "DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/DejaVuSans.ttf",
        "DejaVuSans.ttf",
    ]
    for path in paths:
        p = Path(path)
        if not p.exists():
            continue
        bold = p.parent / "DejaVuSans-Bold.ttf"
        try:
            pdfmetrics.registerFont(TTFont("DejaVuSans", str(p)))
            if bold.exists():
                pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", str(bold)))
            else:
                pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", str(p)))
            logger.info("Шрифт DejaVuSans: %s", p)
            return True
        except Exception as exc:
            logger.warning("DejaVuSans %s: %s", p, exc)
    return False


if _try_register_dejavu():
    FONT_NAME = "DejaVuSans"
    FONT_BOLD = "DejaVuSans-Bold"


def _amount_in_words(amount: float) -> str:
    try:
        from num2words import num2words

        rubles = int(amount)
        kopecks = round((amount - rubles) * 100)
        words = num2words(rubles, lang="ru", to="currency", currency="RUB").capitalize()
        if kopecks:
            words += f" {kopecks:02d} копеек"
        return words
    except Exception as exc:
        logger.warning("num2words: %s", exc)
        return f"{amount:.2f} руб."


def generate_invoice_pdf(
    invoice_number: int,
    invoice_date: date,
    user_full_name: str,
    user_inn: str,
    user_bank_account: str,
    client_name: str,
    service_description: str,
    amount: float,
) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    normal = ParagraphStyle(
        "normal_ru", parent=styles["Normal"], fontName=FONT_NAME, fontSize=10, leading=14
    )
    bold = ParagraphStyle("bold_ru", parent=normal, fontName=FONT_BOLD, fontSize=10)
    title_style = ParagraphStyle(
        "title_ru", parent=normal, fontName=FONT_BOLD, fontSize=14, alignment=1, spaceAfter=6
    )
    subtitle_style = ParagraphStyle(
        "subtitle_ru", parent=normal, fontSize=11, alignment=1, spaceAfter=4
    )
    small = ParagraphStyle("small_ru", parent=normal, fontSize=9)

    story = [
        Paragraph("СЧЁТ НА ОПЛАТУ", title_style),
        Paragraph(f"№ {invoice_number} от {invoice_date.strftime('%d.%m.%Y')}", subtitle_style),
        HRFlowable(width="100%", thickness=2, color=colors.black),
        Spacer(1, 0.4 * cm),
        Paragraph("Исполнитель:", bold),
        Paragraph(f"ФИО: {user_full_name or '—'}", normal),
        Paragraph(f"ИНН: {user_inn or '—'}", normal),
        Paragraph(f"Номер счёта/реквизиты: {user_bank_account or '—'}", normal),
        Spacer(1, 0.4 * cm),
        Paragraph("Заказчик:", bold),
        Paragraph(client_name or "—", normal),
        Spacer(1, 0.5 * cm),
    ]

    col_widths = [1 * cm, 9 * cm, 2 * cm, 3.5 * cm, 3.5 * cm]
    table_data = [
        ["№", "Наименование работ/услуг", "Кол-во", "Цена, руб.", "Сумма, руб."],
        ["1", service_description or "—", "1", f"{amount:,.2f}", f"{amount:,.2f}"],
    ]
    table = Table(table_data, colWidths=col_widths)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4472C4")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
                ("FONTNAME", (0, 1), (-1, -1), FONT_NAME),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("ALIGN", (1, 0), (1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EEF2FF")]),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 0.3 * cm))

    itogo_data = [
        ["", "", "", "ИТОГО:", f"{amount:,.2f} руб."],
        ["", "", "", "НДС:", "Не облагается"],
        ["", "", "", "К оплате:", f"{amount:,.2f} руб."],
    ]
    itogo_table = Table(itogo_data, colWidths=col_widths)
    itogo_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
                ("FONTNAME", (3, 2), (-1, 2), FONT_BOLD),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
                ("LINEABOVE", (3, 0), (-1, 0), 0.5, colors.grey),
            ]
        )
    )
    story.extend([itogo_table, Spacer(1, 0.4 * cm)])
    story.append(Paragraph(f"<b>Итого к оплате:</b> {_amount_in_words(amount)}", normal))
    story.append(Spacer(1, 0.8 * cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Spacer(1, 0.3 * cm))

    sign_table = Table(
        [
            [Paragraph("Исполнитель:", small), Paragraph("", small)],
            [
                Paragraph(
                    f"_________________________ / {user_full_name or '________________'} /",
                    small,
                ),
                Paragraph("М.П.", small),
            ],
        ],
        colWidths=[12 * cm, 5 * cm],
    )
    sign_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
    story.extend([sign_table, Spacer(1, 0.5 * cm)])
    story.append(Paragraph("Счёт действителен в течение 5 банковских дней.", small))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()
