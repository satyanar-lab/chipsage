"""SQLite schema for the chipsage index.

Single file, everything keyed by (vendor, chip, peripheral, register, field). There are no
vendor-specific tables — vendors are data, not code. Provenance (SVD version and source
file) is stored on every chip so that later phases can attach it to every tool response.
"""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 3

SCHEMA_SQL = """
CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE chips (
    id          INTEGER PRIMARY KEY,
    vendor      TEXT NOT NULL,
    name        TEXT NOT NULL,
    svd_version TEXT,
    svd_source  TEXT,
    width       INTEGER NOT NULL DEFAULT 32,
    UNIQUE (vendor, name)
);

CREATE TABLE peripherals (
    id           INTEGER PRIMARY KEY,
    chip_id      INTEGER NOT NULL REFERENCES chips(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    description  TEXT,
    base_address INTEGER NOT NULL,
    size         INTEGER,
    derived_from TEXT,
    UNIQUE (chip_id, name)
);

CREATE TABLE registers (
    id             INTEGER PRIMARY KEY,
    peripheral_id  INTEGER NOT NULL REFERENCES peripherals(id) ON DELETE CASCADE,
    name           TEXT NOT NULL,
    description    TEXT,
    address_offset INTEGER NOT NULL,
    size           INTEGER NOT NULL,
    reset_value    INTEGER,
    reset_mask     INTEGER,
    access         TEXT,
    UNIQUE (peripheral_id, name)
);

CREATE TABLE fields (
    id          INTEGER PRIMARY KEY,
    register_id INTEGER NOT NULL REFERENCES registers(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    description TEXT,
    bit_offset  INTEGER NOT NULL,
    bit_width   INTEGER NOT NULL,
    access      TEXT,
    reset_value INTEGER,
    UNIQUE (register_id, name)
);

CREATE TABLE enums (
    id          INTEGER PRIMARY KEY,
    field_id    INTEGER NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    value       INTEGER,
    description TEXT,
    is_default  INTEGER NOT NULL DEFAULT 0,
    UNIQUE (field_id, name)
);

CREATE INDEX idx_peripherals_chip ON peripherals(chip_id);
CREATE INDEX idx_peripherals_name ON peripherals(name);
CREATE INDEX idx_registers_peripheral ON registers(peripheral_id);
CREATE INDEX idx_registers_name ON registers(name);
CREATE INDEX idx_fields_register ON fields(register_id);
CREATE INDEX idx_enums_field ON enums(field_id);
CREATE INDEX idx_enums_field_value ON enums(field_id, value);

-- Tier-3 documentation: page-anchored prose (FTS5) + peripheral-joined errata.
-- Each document is a vendored datasheet PDF, pinned by SHA-256 for provenance.
CREATE TABLE documents (
    id       INTEGER PRIMARY KEY,
    chip_id  INTEGER NOT NULL REFERENCES chips(id) ON DELETE CASCADE,
    chip     TEXT NOT NULL,
    title    TEXT,
    kind     TEXT NOT NULL DEFAULT 'datasheet',
    source   TEXT NOT NULL,            -- vendored filename, e.g. rp2040-datasheet.pdf
    sha256   TEXT,                     -- provenance pin of the exact PDF indexed
    n_pages  INTEGER,
    UNIQUE (chip, source)
);

-- Full-text index over page prose. chip/page/pdf_page/document_id are stored but UNINDEXED
-- (filter + citation only); `text` is the searchable, verbatim page content.
CREATE VIRTUAL TABLE prose USING fts5(
    text,
    chip UNINDEXED,
    page UNINDEXED,
    pdf_page UNINDEXED,
    document_id UNINDEXED,
    tokenize = 'porter unicode61'
);

CREATE TABLE errata (
    id           INTEGER PRIMARY KEY,
    document_id  INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chip         TEXT NOT NULL,
    code         TEXT NOT NULL,        -- e.g. RP2040-E7
    title        TEXT,                 -- the erratum's Summary line
    peripheral   TEXT,                 -- datasheet hardware-block heading it is grouped under
    page         TEXT,                 -- printed page label (for citation)
    pdf_page     INTEGER,
    text         TEXT NOT NULL,        -- verbatim erratum body
    UNIQUE (chip, code)
);

CREATE INDEX idx_documents_chip ON documents(chip_id);
CREATE INDEX idx_errata_chip ON errata(chip);
CREATE INDEX idx_errata_peripheral ON errata(chip, peripheral);
"""


def create_schema(conn: sqlite3.Connection) -> None:
    """Create the chipsage tables/indexes on a fresh connection and stamp the version."""
    conn.executescript(SCHEMA_SQL)
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    conn.commit()
