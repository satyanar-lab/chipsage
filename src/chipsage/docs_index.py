"""Index vendored datasheet PDFs into the chipsage SQLite database (Tier-3).

For each PDF this inserts one ``documents`` row (pinned by SHA-256 for provenance), one
``prose`` FTS5 row per non-empty page (page-anchored, verbatim), and one ``errata`` row per
erratum found in the datasheet's errata appendix — grouped under the datasheet's own
hardware-block heading so a peripheral query can surface its applicable errata.

The chip must already exist in the index (load its SVD first): a document is keyed to its
chip. No network access — only the local, vendored PDF is read.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .db import connect
from .pdf import document_title, extract_errata, extract_pages, page_count

logger = logging.getLogger("chipsage.docs")

# Datasheet filename -> (chip name, errata code prefix). Filenames are matched case-insensitively
# on substring, so both "rp2040-datasheet.pdf" and a renamed copy resolve.
_CHIP_HINTS: tuple[tuple[str, str, str], ...] = (
    ("rp2040", "RP2040", "RP2040"),
    ("rp2350", "RP2350", "RP2350"),
)


@dataclass
class DocIndexReport:
    """Outcome of indexing one datasheet."""

    chip: str
    source: str
    title: str | None
    pages_indexed: int
    errata_indexed: int
    errata_blocks: list[str]


def chip_for_pdf(path: str | Path) -> tuple[str, str]:
    """Infer ``(chip_name, code_prefix)`` from a datasheet filename."""
    name = Path(path).name.lower()
    for needle, chip, prefix in _CHIP_HINTS:
        if needle in name:
            return chip, prefix
    raise ValueError(
        f"cannot infer chip from PDF filename {Path(path).name!r}; "
        f"expected it to contain one of: {[h[0] for h in _CHIP_HINTS]}"
    )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def index_document(
    conn: sqlite3.Connection,
    pdf_path: str | Path,
    chip: str | None = None,
    kind: str = "datasheet",
) -> DocIndexReport:
    """Index one datasheet PDF (prose + errata) into ``conn`` for its chip."""
    pdf_path = Path(pdf_path)
    inferred_chip, code_prefix = chip_for_pdf(pdf_path)
    chip = chip or inferred_chip

    chip_row = conn.execute(
        "SELECT id FROM chips WHERE name = ? COLLATE NOCASE", (chip,)
    ).fetchone()
    if chip_row is None:
        raise ValueError(
            f"chip {chip!r} is not in the index; load its SVD before indexing its datasheet"
        )
    chip_id = chip_row["id"]

    title = document_title(pdf_path)
    n_pages = page_count(pdf_path)
    sha = _sha256(pdf_path)

    cur = conn.cursor()
    cur.execute(
        "INSERT INTO documents (chip_id, chip, title, kind, source, sha256, n_pages) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (chip_id, chip, title, kind, pdf_path.name, sha, n_pages),
    )
    document_id = cur.lastrowid

    pages_indexed = 0
    for page in extract_pages(pdf_path):
        if not page.text.strip():
            continue  # blank pages contribute nothing to search
        cur.execute(
            "INSERT INTO prose (text, chip, page, pdf_page, document_id) VALUES (?, ?, ?, ?, ?)",
            (page.text, chip, page.label, page.pdf_page, document_id),
        )
        pages_indexed += 1

    errata_indexed = 0
    blocks: list[str] = []
    for erratum in extract_errata(pdf_path, code_prefix):
        cur.execute(
            "INSERT INTO errata (document_id, chip, code, title, peripheral, page, pdf_page, "
            "text) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                document_id,
                chip,
                erratum.code,
                erratum.title,
                erratum.peripheral,
                erratum.label,
                erratum.pdf_page,
                erratum.text,
            ),
        )
        errata_indexed += 1
        if erratum.peripheral and erratum.peripheral not in blocks:
            blocks.append(erratum.peripheral)

    conn.commit()
    logger.info(
        "indexed %s: %d pages, %d errata (%s)", pdf_path.name, pages_indexed, errata_indexed, chip
    )
    return DocIndexReport(
        chip=chip,
        source=pdf_path.name,
        title=title,
        pages_indexed=pages_indexed,
        errata_indexed=errata_indexed,
        errata_blocks=sorted(blocks),
    )


def index_documents(
    db_path: str | Path, pdf_paths: list[str | Path]
) -> list[DocIndexReport]:
    """Open an existing index read-write and index each datasheet PDF into it."""
    conn = connect(db_path)
    try:
        return [index_document(conn, pdf) for pdf in pdf_paths]
    finally:
        conn.close()
