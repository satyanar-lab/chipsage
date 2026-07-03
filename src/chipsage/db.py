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


def connect_ro(path: str | Path) -> sqlite3.Connection:
    """Open an existing index read-only.

    The MCP tools never write, so the server uses this: it opens the SQLite file in ``mode=ro``
    (which fails cleanly if the file is missing) and guarantees no tool call can mutate the
    index. Raises :class:`FileNotFoundError` with a helpful message when the file is absent.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"chipsage index not found: {path} — build it with `chipsage-build` "
            f"or point --db / $CHIPSAGE_DB at an existing index"
        )
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn
