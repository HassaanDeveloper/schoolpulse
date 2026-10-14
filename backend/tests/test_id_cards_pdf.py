import re

import pytest

from backend.services.id_cards import CardData, render_cards_pdf


def _cards(count: int) -> list[CardData]:
    return [
        CardData(
            student_name=f"Student {i} Khan",
            admission_number=f"SP-{i:03d}",
            class_label="Grade 5 - A",
            credential=f"token-{i}-" + "x" * 30,
        )
        for i in range(count)
    ]


def _page_count(pdf: bytes) -> int:
    return len(re.findall(rb"/Type /Page(?![A-Za-z])", pdf))


def test_pdf_is_generated():
    pdf = render_cards_pdf("Karachi Model School", _cards(3))
    assert pdf.startswith(b"%PDF")


def test_ten_cards_fit_on_one_page_and_eleven_need_two():
    assert _page_count(render_cards_pdf("Karachi Model School", _cards(10))) == 1
    assert _page_count(render_cards_pdf("Karachi Model School", _cards(11))) == 2


def test_non_latin_names_do_not_crash():
    card = CardData(
        student_name="علی خان",
        admission_number="SP-001",
        class_label="Grade 5 - A",
        credential="token-" + "x" * 30,
    )
    assert render_cards_pdf("Karachi Model School", [card]).startswith(b"%PDF")


def test_empty_list_is_rejected():
    with pytest.raises(ValueError):
        render_cards_pdf("Karachi Model School", [])