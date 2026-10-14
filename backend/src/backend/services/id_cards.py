"""Printable student ID cards.

Builds an A4 PDF with ten cards per sheet (2 columns x 5 rows). Each card is
85.6 x 54 mm, the standard ID-card size, with dashed cut guides.

The PDF contains live QR credentials. Treat it like a stack of keys: print it,
then delete it.

Limitation: names are drawn with the built-in Latin fonts. Characters outside
Latin-1 (for example Urdu script) are replaced with "?". Use Latin spellings
of names on the card until a font is bundled.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

CARD_W = 85.6 * mm
CARD_H = 54.0 * mm
COLS = 2
ROWS = 5
PER_PAGE = COLS * ROWS
QR_SIZE = 34 * mm
PAD = 4 * mm


@dataclass(frozen=True)
class CardData:
    student_name: str
    admission_number: str
    class_label: str
    credential: str


def _safe(text: str) -> str:
    """Keep only characters the built-in fonts can draw."""
    return text.encode("latin-1", "replace").decode("latin-1")


def _fit_font_size(text: str, font: str, start: float, max_width: float, minimum: float = 6.0) -> float:
    size = start
    while size > minimum and pdfmetrics.stringWidth(text, font, size) > max_width:
        size -= 0.5
    return size


def _draw_card(c: canvas.Canvas, x: float, y: float, school_name: str, card: CardData) -> None:
    # Dashed cut guide.
    c.saveState()
    c.setStrokeColorRGB(0.7, 0.7, 0.7)
    c.setLineWidth(0.4)
    c.setDash(2, 2)
    c.rect(x, y, CARD_W, CARD_H)
    c.restoreState()

    # Header: school name and a rule.
    school = _safe(school_name)
    size = _fit_font_size(school, "Helvetica-Bold", 9, CARD_W - 2 * PAD)
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", size)
    c.drawString(x + PAD, y + CARD_H - 7 * mm, school)
    c.setStrokeColorRGB(0.2, 0.2, 0.2)
    c.setLineWidth(0.6)
    c.line(x + PAD, y + CARD_H - 9 * mm, x + CARD_W - PAD, y + CARD_H - 9 * mm)

    # QR code, error-correction level M, with its own quiet zone.
    widget = qr.QrCodeWidget(card.credential, barLevel="M", barBorder=2)
    bounds = widget.getBounds()
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    drawing = Drawing(QR_SIZE, QR_SIZE, transform=[QR_SIZE / width, 0, 0, QR_SIZE / height, 0, 0])
    drawing.add(widget)
    renderPDF.draw(drawing, c, x + PAD, y + 5 * mm)

    # Student details on the right.
    tx = x + PAD + QR_SIZE + 4 * mm
    tw = CARD_W - (tx - x) - PAD

    ty = y + 36 * mm
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 12)
    for line in simpleSplit(_safe(card.student_name), "Helvetica-Bold", 12, tw)[:2]:
        c.drawString(tx, ty, line)
        ty -= 5.5 * mm

    def labelled(label: str, value: str, label_y: float, value_y: float, bold: bool = False) -> None:
        c.setFillColorRGB(0.4, 0.4, 0.4)
        c.setFont("Helvetica", 7.5)
        c.drawString(tx, label_y, label)
        font = "Helvetica-Bold" if bold else "Helvetica"
        text = _safe(value)
        c.setFillColorRGB(0, 0, 0)
        c.setFont(font, _fit_font_size(text, font, 10, tw))
        c.drawString(tx, value_y, text)

    labelled("CLASS", card.class_label, y + 20 * mm, y + 15.5 * mm)
    labelled("ADMISSION NO.", card.admission_number, y + 10 * mm, y + 5.5 * mm, bold=True)


def render_cards_pdf(school_name: str, cards: list[CardData]) -> bytes:
    if not cards:
        raise ValueError("At least one card is required.")

    buffer = io.BytesIO()
    page_w, page_h = A4
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle("SchoolPulse student cards")

    left = (page_w - COLS * CARD_W) / 2
    top = (page_h - ROWS * CARD_H) / 2

    for index, card in enumerate(cards):
        slot = index % PER_PAGE
        if index and slot == 0:
            c.showPage()
        col = slot % COLS
        row = slot // COLS
        x = left + col * CARD_W
        y = page_h - top - (row + 1) * CARD_H
        _draw_card(c, x, y, school_name, card)

    c.save()
    return buffer.getvalue()