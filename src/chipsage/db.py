"""SQLite connection helpers.

Centralises the pragmas every chipsage connection needs: foreign keys enforced (so the
CASCADE relationships in the schema actually hold) and ``sqlite3.Row`` for name-based access.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    """Open a SQLite connection with chipsage's standard pragmas applied."""
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
