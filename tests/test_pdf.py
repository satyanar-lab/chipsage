"""Tests for the PyMuPDF-isolating extractor against the real vendored datasheets.

These prove Tier-3 extraction is verbatim and page-anchored, and that the errata parser
recovers the datasheet's own per-hardware-block grouping (the peripheral join).
"""

from __future__ import annotations

from itertools import islice
from pathlib import Path

from chipsage import pdf
from chipsage.models import Erratum, PageText

# Ground-truth facts read from the pinned PDFs (see data/pdf/SOURCES.md).
RP2040_PAGES = 642
RP2350_PAGES = 1380
RP2040_USB_ERRATA = {
    "RP2040-E2",
    "RP2040-E3",
    "RP2040-E4",
    "RP2040-E5",
    "RP2040-E15",
    "RP2040-E16",
}


def test_page_count_and_title(rp2040_pdf: Path) -> None:
    assert pdf.page_count(rp2040_pdf) == RP2040_PAGES
    assert "RP2040" in (pdf.document_title(rp2040_pdf) or "")


def test_extract_pages_are_page_anchored(rp2040_pdf: Path) -> None:
    pages = list(islice(pdf.extract_pages(rp2040_pdf), 4))
    assert all(isinstance(p, PageText) for p in pages)
    assert [p.pdf_page for p in pages] == [1, 2, 3, 4]
    assert all(p.label for p in pages)  # every page carries a printed label for citation


def test_rp2040_errata_grouped_by_hardware_block(rp2040_pdf: Path) -> None:
    errata = pdf.extract_errata(rp2040_pdf, "RP2040")
    assert all(isinstance(e, Erratum) for e in errata)

    by_code = {e.code: e for e in errata}
    assert set(by_code) == {f"RP2040-E{n}" for n in range(1, 17)}  # E1..E16, no more, no fewer

    # every erratum is grouped under a hardware block (the peripheral join)
    assert all(e.peripheral for e in errata)

    # the datasheet lists the two clock errata under "Clocks"
    assert by_code["RP2040-E7"].peripheral == "Clocks"
    assert by_code["RP2040-E10"].peripheral == "Clocks"

    # the USB block collects all six USB errata
    usb = {code for code, e in by_code.items() if e.peripheral == "USB"}
    assert usb == RP2040_USB_ERRATA


def test_errata_body_is_verbatim_and_structured(rp2040_pdf: Path) -> None:
    e7 = next(e for e in pdf.extract_errata(rp2040_pdf, "RP2040") if e.code == "RP2040-E7")
    assert e7.title == "ROSC and XOSC COUNT registers are unreliable"
    # section structure preserved from the datasheet
    assert "Description" in e7.text
    assert "Workaround" in e7.text
    # a verbatim phrase from the datasheet body — extracted, not paraphrased
    assert "synchronisation issue" in e7.text
    assert e7.label  # page anchor present


def test_errata_text_has_no_running_footer_leakage(rp2040_pdf: Path) -> None:
    # Regression: the page footer (doc title / block name / page number) uses RobotoSlab and
    # must never leak into an erratum's title or body.
    errata = pdf.extract_errata(rp2040_pdf, "RP2040")
    blocks = {e.peripheral for e in errata if e.peripheral}
    for e in errata:
        assert "RP2040 Datasheet" not in e.text
        title = (e.title or "").rstrip()
        # a title must not end with a *different* block's heading pasted on from the footer
        assert not any(title.endswith(b) and title != b for b in blocks)


def test_rp2350_errata_parser_generalises(rp2350_pdf: Path) -> None:
    errata = pdf.extract_errata(rp2350_pdf, "RP2350")
    codes = {e.code for e in errata}
    assert len(codes) == 28
    assert "RP2350-E1" in codes and "RP2350-E28" in codes
    # the same font-driven grouping recovers a hardware block for every RP2350 erratum too
    assert all(e.peripheral for e in errata)
