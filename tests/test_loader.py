"""Integration tests: load the real vendored SVDs, and prove the rejection path with a
hand-built chip containing deliberate violations."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import pytest

from chipsage.build_index import main as build_main
from chipsage.loader import build_database, insert_chip, load_svd
from chipsage.models import AddressBlock, Chip, EnumeratedValue, Field, Peripheral, Register
from chipsage.schema import SCHEMA_VERSION

# Ground-truth facts read directly from the pinned SVD files (see data/svd/SOURCES.md).
RP2040_PERIPHERALS = 37
RP2350_PERIPHERALS = 54
SIO_BASE = 0xD000_0000
CHIP_ID_RESET = 536_881_447  # SYSINFO.CHIP_ID reset value in RP2040.svd


def _one(db: sqlite3.Connection, sql: str, *params: object) -> sqlite3.Row | None:
    return db.execute(sql, params).fetchone()


def _peripheral_base(db: sqlite3.Connection, chip: str, name: str) -> int | None:
    row = _one(
        db,
        "SELECT p.base_address FROM peripherals p JOIN chips c ON c.id = p.chip_id "
        "WHERE c.name = ? AND p.name = ?",
        chip,
        name,
    )
    return row["base_address"] if row else None


# --- real SVD: RP2040 ---------------------------------------------------------------------


def test_rp2040_loads_cleanly_with_provenance(db: sqlite3.Connection, rp2040_path: Path) -> None:
    report = load_svd(rp2040_path, db)

    assert report.vendor == "Raspberry Pi"
    assert report.clean  # no rejections on clean vendor data
    assert report.violations == []
    assert report.registers_rejected == 0
    assert report.fields_rejected == 0
    assert report.peripherals == RP2040_PERIPHERALS

    chip = _one(db, "SELECT * FROM chips WHERE name = 'RP2040'")
    assert chip is not None
    assert chip["vendor"] == "Raspberry Pi"
    assert chip["svd_version"] == "0.1"
    assert chip["svd_source"] == "RP2040.svd"  # provenance recorded

    # inserted counts match what actually landed in the tables
    (n_regs,) = _one(db, "SELECT COUNT(*) FROM registers")
    (n_fields,) = _one(db, "SELECT COUNT(*) FROM fields")
    assert n_regs == report.registers_inserted
    assert n_fields == report.fields_inserted


def test_rp2040_known_register_and_fields(db: sqlite3.Connection, rp2040_path: Path) -> None:
    load_svd(rp2040_path, db)

    assert _peripheral_base(db, "RP2040", "SIO") == SIO_BASE

    chip_id = _one(
        db,
        "SELECT r.* FROM registers r "
        "JOIN peripherals p ON p.id = r.peripheral_id "
        "JOIN chips c ON c.id = p.chip_id "
        "WHERE c.name = 'RP2040' AND p.name = 'SYSINFO' AND r.name = 'CHIP_ID'",
    )
    assert chip_id is not None
    assert chip_id["address_offset"] == 0x0
    assert chip_id["size"] == 32
    assert chip_id["reset_value"] == CHIP_ID_RESET
    assert chip_id["access"] == "read-write"

    fields = {
        row["name"]: row
        for row in db.execute(
            "SELECT * FROM fields WHERE register_id = ?", (chip_id["id"],)
        ).fetchall()
    }
    assert fields["REVISION"]["bit_offset"] == 28
    assert fields["REVISION"]["bit_width"] == 4
    assert fields["PART"]["bit_offset"] == 12
    assert fields["PART"]["bit_width"] == 16
    assert fields["MANUFACTURER"]["bit_offset"] == 0
    assert fields["MANUFACTURER"]["bit_width"] == 12


def test_rp2040_field_reset_values_are_extracted_from_register(
    db: sqlite3.Connection, rp2040_path: Path
) -> None:
    # Each field's stored reset is its slice of the register reset value; anchored to the
    # independently-known register constant, not re-derived from the loader.
    load_svd(rp2040_path, db)
    rows = db.execute(
        "SELECT f.name, f.reset_value FROM fields f "
        "JOIN registers r ON r.id = f.register_id "
        "JOIN peripherals p ON p.id = r.peripheral_id "
        "WHERE p.name = 'SYSINFO' AND r.name = 'CHIP_ID'"
    ).fetchall()
    reset = {row["name"]: row["reset_value"] for row in rows}
    assert reset["MANUFACTURER"] == (CHIP_ID_RESET & 0xFFF)
    assert reset["PART"] == ((CHIP_ID_RESET >> 12) & 0xFFFF)
    assert reset["REVISION"] == ((CHIP_ID_RESET >> 28) & 0xF)


def test_rp2040_derived_peripheral_resolved(db: sqlite3.Connection, rp2040_path: Path) -> None:
    # I2C1 derives from I2C0: it must carry the provenance note *and* the inherited registers.
    load_svd(rp2040_path, db)
    i2c1 = _one(
        db,
        "SELECT p.*, (SELECT COUNT(*) FROM registers r WHERE r.peripheral_id = p.id) AS nregs "
        "FROM peripherals p JOIN chips c ON c.id = p.chip_id "
        "WHERE c.name = 'RP2040' AND p.name = 'I2C1'",
    )
    assert i2c1 is not None
    assert i2c1["base_address"] == 0x4004_8000
    assert i2c1["derived_from"] == "I2C0"
    assert i2c1["nregs"] == 42


# --- real SVD: RP2350 ---------------------------------------------------------------------


def test_rp2350_loads_cleanly(db: sqlite3.Connection, rp2350_path: Path) -> None:
    report = load_svd(rp2350_path, db)
    assert report.vendor == "Raspberry Pi"
    assert report.clean
    assert report.peripherals == RP2350_PERIPHERALS
    assert _peripheral_base(db, "RP2350", "SIO") == SIO_BASE
    # a peripheral unique to RP2350 is present
    assert _peripheral_base(db, "RP2350", "SHA256") is not None


# --- both chips in one index --------------------------------------------------------------


def test_build_database_writes_file_with_both_chips(
    tmp_path: Path, rp2040_path: Path, rp2350_path: Path
) -> None:
    db_path = tmp_path / "chipsage.db"
    reports = build_database([rp2040_path, rp2350_path], db_path)

    assert db_path.is_file()
    assert [r.chip for r in reports] == ["RP2040", "RP2350"]
    assert all(r.clean for r in reports)

    from chipsage.db import connect

    conn = connect(db_path)
    try:
        (n_chips,) = _one(conn, "SELECT COUNT(*) FROM chips")
        assert n_chips == 2
        schema = _one(conn, "SELECT value FROM meta WHERE key = 'schema_version'")
        assert schema["value"] == str(SCHEMA_VERSION)
    finally:
        conn.close()


def test_build_cli_smoke(tmp_path: Path, rp2040_path: Path) -> None:
    out = tmp_path / "cli.db"
    rc = build_main(["--svd", str(rp2040_path), "-o", str(out), "--strict"])
    assert rc == 0
    assert out.is_file()


# --- rejection path (synthetic violations) ------------------------------------------------


def _chip_with_violations() -> Chip:
    return Chip(
        vendor="Test",
        name="TESTMCU",
        svd_version="1.0",
        svd_source="synthetic",
        peripherals=(
            Peripheral(
                name="P1",
                base_address=0x4000_0000,
                address_blocks=(AddressBlock(0, 0x100),),
                registers=(
                    # clean — kept
                    Register(
                        "GOOD",
                        0x00,
                        32,
                        reset_value=0x1,
                        fields=(Field("EN", 0, 1, reset_value=1),),
                    ),
                    # overlapping fields — whole register rejected
                    Register("OVERLAP", 0x04, 32, fields=(Field("A", 0, 4), Field("B", 2, 4))),
                    # address past the 0x100 block — rejected
                    Register("OOR", 0x200, 32),
                    # reset too wide for the 8-bit register — rejected
                    Register("BIGRESET", 0x08, 8, reset_value=0x1FF),
                    # one bad field, register otherwise fine — field dropped, register kept
                    Register(
                        "BADFIELD", 0x0C, 8, fields=(Field("OK", 0, 4), Field("TOOBIG", 4, 8))
                    ),
                ),
            ),
        ),
    )


def test_insert_rejects_and_logs_violations(
    db: sqlite3.Connection, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="chipsage.loader"):
        report = insert_chip(db, _chip_with_violations())

    # counts: OVERLAP, OOR, BIGRESET rejected (register scope); TOOBIG rejected (field scope)
    assert report.registers_rejected == 3
    assert report.registers_inserted == 2  # GOOD, BADFIELD
    assert report.fields_rejected == 1
    assert not report.clean

    rules = {v.rule for v in report.violations}
    assert rules == {
        "field_overlap",
        "address_out_of_range",
        "reset_overflow",
        "field_out_of_range",
    }

    # violations were actually logged
    assert "rejected register" in caplog.text
    assert "rejected field" in caplog.text

    # database contains only the valid rows
    kept_regs = {row["name"] for row in db.execute("SELECT name FROM registers").fetchall()}
    assert kept_regs == {"GOOD", "BADFIELD"}

    kept_fields = {row["name"] for row in db.execute("SELECT name FROM fields").fetchall()}
    assert kept_fields == {"EN", "OK"}  # TOOBIG dropped, its register's OK field survives


# --- enumerated values --------------------------------------------------------------------


def test_enums_loaded_for_real_svd(db: sqlite3.Connection, rp2040_path: Path) -> None:
    report = load_svd(rp2040_path, db)
    assert report.enums_inserted > 2000
    assert report.enums_rejected == 0
    rows = db.execute(
        "SELECT e.value, e.name FROM enums e "
        "JOIN fields f ON f.id = e.field_id "
        "JOIN registers r ON r.id = f.register_id "
        "JOIN peripherals p ON p.id = r.peripheral_id "
        "WHERE p.name = 'CLOCKS' AND r.name = 'CLK_REF_CTRL' AND f.name = 'SRC' "
        "ORDER BY e.value"
    ).fetchall()
    assert [(x["value"], x["name"]) for x in rows] == [
        (0, "rosc_clksrc_ph"),
        (1, "clksrc_clk_ref_aux"),
        (2, "xosc_clksrc"),
    ]


def test_insert_rejects_oversized_enum(db: sqlite3.Connection) -> None:
    chip = Chip(
        vendor="Test",
        name="ENUMMCU",
        peripherals=(
            Peripheral(
                name="P1",
                base_address=0x4000_0000,
                address_blocks=(AddressBlock(0, 0x100),),
                registers=(
                    Register(
                        "R",
                        0x00,
                        32,
                        fields=(
                            Field(
                                "MODE",
                                0,
                                2,  # 2-bit field, max value 3
                                enumerated_values=(
                                    EnumeratedValue("ok", 3),
                                    EnumeratedValue("bad", 8),  # does not fit 2 bits
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    report = insert_chip(db, chip)
    assert report.enums_inserted == 1
    assert report.enums_rejected == 1
    assert any(v.rule == "enum_out_of_range" for v in report.violations)
    assert {r["name"] for r in db.execute("SELECT name FROM enums").fetchall()} == {"ok"}
