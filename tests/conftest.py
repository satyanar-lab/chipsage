"""Shared pytest fixtures: paths to the vendored SVDs and a fresh in-memory database."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from chipsage.db import connect, connect_ro
from chipsage.docs_index import index_documents
from chipsage.loader import build_database
from chipsage.schema import create_schema

ROOT = Path(__file__).resolve().parent.parent
SVD_DIR = ROOT / "data" / "svd"
PDF_DIR = ROOT / "data" / "pdf"


@pytest.fixture
def rp2040_path() -> Path:
    return SVD_DIR / "RP2040.svd"


@pytest.fixture
def rp2350_path() -> Path:
    return SVD_DIR / "RP2350.svd"


@pytest.fixture
def rp2040_pdf() -> Path:
    return PDF_DIR / "rp2040-datasheet.pdf"


@pytest.fixture
def rp2350_pdf() -> Path:
    return PDF_DIR / "rp2350-datasheet.pdf"


@pytest.fixture
def db() -> Iterator[sqlite3.Connection]:
    """A fresh in-memory SQLite connection with the chipsage schema created."""
    conn = connect(":memory:")
    create_schema(conn)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture(scope="session")
def built_db_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the index from both vendored SVDs once per session; return its file path."""
    path = tmp_path_factory.mktemp("index") / "chipsage.db"
    build_database([SVD_DIR / "RP2040.svd", SVD_DIR / "RP2350.svd"], path)
    return path


@pytest.fixture
def qconn(built_db_path: Path) -> Iterator[sqlite3.Connection]:
    """A read-only connection to the session-built index (as the MCP server opens it)."""
    conn = connect_ro(built_db_path)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture(scope="session")
def docs_db_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A full index (both SVDs + the RP2040 datasheet's Tier-3 prose & errata), built once.

    Only the RP2040 datasheet is indexed here to keep the fixture fast; RP2350 errata parsing
    is covered directly against the PDF in ``test_pdf.py``.
    """
    path = tmp_path_factory.mktemp("docs-index") / "chipsage.db"
    build_database([SVD_DIR / "RP2040.svd", SVD_DIR / "RP2350.svd"], path)
    index_documents(path, [PDF_DIR / "rp2040-datasheet.pdf"])
    return path


@pytest.fixture
def docs_qconn(docs_db_path: Path) -> Iterator[sqlite3.Connection]:
    """A read-only connection to the docs-inclusive index."""
    conn = connect_ro(docs_db_path)
    try:
        yield conn
    finally:
        conn.close()
