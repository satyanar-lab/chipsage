"""Tests for the Tier-3 datasheet indexer (documents + prose FTS5 + errata)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from chipsage.docs_index import chip_for_pdf, index_document
from chipsage.loader import load_svd


def test_chip_for_pdf_infers_from_filename() -> None:
    assert chip_for_pdf("data/pdf/rp2040-datasheet.pdf") == ("RP2040", "RP2040")
    assert chip_for_pdf("RP2350-Datasheet.PDF") == ("RP2350", "RP2350")
    with pytest.raises(ValueError):
        chip_for_pdf("mystery-part.pdf")


def test_index_document_populates_prose_and_errata(
    db: sqlite3.Connection, rp2040_path: Path, rp2040_pdf: Path
) -> None:
    load_svd(rp2040_path, db)  # the chip must exist before its datasheet is indexed
    report = index_document(db, rp2040_pdf)

    assert report.chip == "RP2040"
    assert report.pages_indexed > 600
    assert report.errata_indexed == 16
    assert {"Clocks", "USB", "DMA"} <= set(report.errata_blocks)

    (n_docs,) = db.execute("SELECT COUNT(*) FROM documents").fetchone()
    assert n_docs == 1
    (n_prose,) = db.execute("SELECT COUNT(*) FROM prose").fetchone()
    assert n_prose == report.pages_indexed
    (n_errata,) = db.execute("SELECT COUNT(*) FROM errata").fetchone()
    assert n_errata == 16

    # provenance: the exact PDF is pinned by SHA-256
    row = db.execute("SELECT sha256, title, source FROM documents").fetchone()
    assert row["sha256"] and len(row["sha256"]) == 64
    assert row["source"] == "rp2040-datasheet.pdf"

    # FTS5 search works against the freshly-indexed prose
    hit = db.execute(
        "SELECT page FROM prose WHERE prose MATCH 'watchdog' ORDER BY rank LIMIT 1"
    ).fetchone()
    assert hit is not None


def test_index_document_requires_chip_loaded(db: sqlite3.Connection, rp2040_pdf: Path) -> None:
    # no SVD loaded → the RP2040 chip row does not exist yet
    with pytest.raises(ValueError, match="not in the index"):
        index_document(db, rp2040_pdf)
