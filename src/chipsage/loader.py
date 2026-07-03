"""Validate a parsed chip and load its valid rows into SQLite.

Flow: :func:`chipsage.svd.parse_svd` builds a domain :class:`~chipsage.models.Chip`; this
module validates every register and field and inserts only the ones that pass. Rejected
entities are logged (``chipsage.loader`` logger) and recorded on the :class:`LoadReport` —
never repaired. Real vendor SVDs validate cleanly, so the rejection path exists to keep
malformed or community SVDs from silently poisoning the index.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path

from .db import connect
from .models import Chip
from .schema import create_schema
from .svd import parse_svd
from .validation import Violation, validate_field, validate_register

logger = logging.getLogger("chipsage.loader")


@dataclass
class LoadReport:
    """Outcome of loading one chip: how much landed, how much was rejected, and why."""

    chip: str
    vendor: str
    peripherals: int = 0
    registers_inserted: int = 0
    registers_rejected: int = 0
    fields_inserted: int = 0
    fields_rejected: int = 0
    violations: list[Violation] = dataclass_field(default_factory=list)

    @property
    def clean(self) -> bool:
        """True when nothing was rejected."""
        return not self.violations


def insert_chip(conn: sqlite3.Connection, chip: Chip) -> LoadReport:
    """Validate ``chip`` and insert its valid peripherals/registers/fields into ``conn``.

    Returns a :class:`LoadReport`. A register with any register-scope violation is skipped
    entirely (its fields never reach the database); a field-scope violation skips only that
    field. Runs in a single transaction.
    """
    report = LoadReport(chip=chip.name, vendor=chip.vendor)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO chips (vendor, name, svd_version, svd_source, width) VALUES (?, ?, ?, ?, ?)",
        (chip.vendor, chip.name, chip.svd_version, chip.svd_source, chip.width),
    )
    chip_id = cur.lastrowid

    for peripheral in chip.peripherals:
        report.peripherals += 1
        cur.execute(
            "INSERT INTO peripherals (chip_id, name, description, base_address, size, "
            "derived_from) VALUES (?, ?, ?, ?, ?, ?)",
            (
                chip_id,
                peripheral.name,
                peripheral.description,
                peripheral.base_address,
                peripheral.size,
                peripheral.derived_from,
            ),
        )
        peripheral_id = cur.lastrowid

        for register in peripheral.registers:
            reg_violations = validate_register(register, peripheral)
            if reg_violations:
                report.registers_rejected += 1
                for violation in reg_violations:
                    report.violations.append(violation)
                    logger.warning("rejected register %s", violation)
                continue

            cur.execute(
                "INSERT INTO registers (peripheral_id, name, description, address_offset, "
                "size, reset_value, reset_mask, access) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    peripheral_id,
                    register.name,
                    register.description,
                    register.address_offset,
                    register.size,
                    register.reset_value,
                    register.reset_mask,
                    register.access,
                ),
            )
            register_id = cur.lastrowid
            report.registers_inserted += 1

            for fld in register.fields:
                field_violations = validate_field(fld, register, peripheral)
                if field_violations:
                    report.fields_rejected += 1
                    for violation in field_violations:
                        report.violations.append(violation)
                        logger.warning("rejected field %s", violation)
                    continue

                cur.execute(
                    "INSERT INTO fields (register_id, name, description, bit_offset, "
                    "bit_width, access, reset_value) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        register_id,
                        fld.name,
                        fld.description,
                        fld.bit_offset,
                        fld.bit_width,
                        fld.access,
                        fld.reset_value,
                    ),
                )
                report.fields_inserted += 1

    conn.commit()
    return report


def load_svd(path: str | Path, conn: sqlite3.Connection) -> LoadReport:
    """Parse an SVD file and load it into an existing (schema-created) connection."""
    return insert_chip(conn, parse_svd(path))


def build_database(svd_paths: list[str | Path], db_path: str | Path) -> list[LoadReport]:
    """Create a fresh schema at ``db_path`` and load every SVD in ``svd_paths`` into it."""
    conn = connect(db_path)
    try:
        create_schema(conn)
        return [load_svd(path, conn) for path in svd_paths]
    finally:
        conn.close()
