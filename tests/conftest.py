"""Shared pytest fixtures: paths to the vendored SVDs and a fresh in-memory database."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from chipsage.db import connect
from chipsage.schema import create_schema

SVD_DIR = Path(__file__).resolve().parent.parent / "data" / "svd"


@pytest.fixture
def rp2040_path() -> Path:
    return SVD_DIR / "RP2040.svd"


@pytest.fixture
def rp2350_path() -> Path:
    return SVD_DIR / "RP2350.svd"


@pytest.fixture
def db() -> Iterator[sqlite3.Connection]:
    """A fresh in-memory SQLite connection with the chipsage schema created."""
    conn = connect(":memory:")
    create_schema(conn)
    try:
        yield conn
    finally:
        conn.close()
