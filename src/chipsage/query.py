"""Citation-backed query layer over the chipsage SQLite index.

Every result carries provenance (vendor, chip, SVD version, source file) — nothing leaves a
tool without a source reference, per the Constitution. These functions are the deterministic
core that the MCP server wraps: they take an open ``sqlite3`` connection and return
JSON-ready dicts. All lookups are read-only and make no network calls.

Numeric quantities that engineers read in hex (addresses, reset values, field values) are
returned as ``0x``-prefixed strings; bit positions and widths are returned as integers.
"""

from __future__ import annotations

import difflib
import sqlite3

from .bits import (
    FieldSpec,
    analyze_write,
    decode_fields,
    effective_access,
    has_errors,
    size_mask,
    undefined_mask,
)


class ChipsageQueryError(ValueError):
    """A requested chip / peripheral / register could not be resolved."""


def _hex(value: int | None, size_bits: int = 32) -> str | None:
    if value is None:
        return None
    width = max(1, (size_bits + 3) // 4)
    return f"0x{value:0{width}X}"


def _bits_label(bit_offset: int, bit_width: int) -> str:
    msb = bit_offset + bit_width - 1
    return f"[{bit_offset}]" if bit_width == 1 else f"[{msb}:{bit_offset}]"


def _did_you_mean(term: str, names: list[str]) -> str:
    upper = {n.upper(): n for n in names}
    close = difflib.get_close_matches(term.upper(), list(upper), n=3)
    if close:
        return f"; did you mean {[upper[c] for c in close]}?"
    listed = sorted(names)
    shown = listed[:12]
    tail = "" if len(listed) <= 12 else f" (+{len(listed) - 12} more)"
    return f"; available: {shown}{tail}"


# --- resolution ---------------------------------------------------------------------------


def resolve_chip_row(conn: sqlite3.Connection, chip: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM chips WHERE name = ? COLLATE NOCASE", (chip,)
    ).fetchone()
    if row is None:
        available = [r["name"] for r in conn.execute("SELECT name FROM chips ORDER BY name")]
        raise ChipsageQueryError(f"unknown chip {chip!r}; indexed chips: {available}")
    return row


def resolve_register_by_name(
    conn: sqlite3.Connection, chip_row: sqlite3.Row, peripheral: str, register: str
) -> tuple[sqlite3.Row, sqlite3.Row]:
    prow = conn.execute(
        "SELECT * FROM peripherals WHERE chip_id = ? AND name = ? COLLATE NOCASE",
        (chip_row["id"], peripheral),
    ).fetchone()
    if prow is None:
        names = [r["name"] for r in conn.execute(
            "SELECT name FROM peripherals WHERE chip_id = ?", (chip_row["id"],))]
        raise ChipsageQueryError(
            f"unknown peripheral {peripheral!r} on {chip_row['name']}"
            + _did_you_mean(peripheral, names)
        )
    rrow = conn.execute(
        "SELECT * FROM registers WHERE peripheral_id = ? AND name = ? COLLATE NOCASE",
        (prow["id"], register),
    ).fetchone()
    if rrow is None:
        names = [r["name"] for r in conn.execute(
            "SELECT name FROM registers WHERE peripheral_id = ?", (prow["id"],))]
        raise ChipsageQueryError(
            f"unknown register {register!r} in {chip_row['name']}.{prow['name']}"
            + _did_you_mean(register, names)
        )
    return prow, rrow


def resolve_register_by_address(
    conn: sqlite3.Connection, chip_row: sqlite3.Row, address: int
) -> tuple[sqlite3.Row, sqlite3.Row]:
    prow = conn.execute(
        "SELECT * FROM peripherals WHERE chip_id = ? AND base_address <= ? "
        "AND (size IS NULL OR ? < base_address + size) "
        "ORDER BY base_address DESC LIMIT 1",
        (chip_row["id"], address, address),
    ).fetchone()
    if prow is None:
        raise ChipsageQueryError(
            f"address {address:#x} is not within any {chip_row['name']} peripheral"
        )
    offset = address - prow["base_address"]
    rrow = conn.execute(
        "SELECT * FROM registers WHERE peripheral_id = ? AND address_offset = ?",
        (prow["id"], offset),
    ).fetchone()
    if rrow is None:
        raise ChipsageQueryError(
            f"address {address:#x} falls in peripheral {prow['name']} "
            f"(base {prow['base_address']:#x}) but no register is defined at offset {offset:#x}"
        )
    return prow, rrow


def _resolve(
    conn: sqlite3.Connection,
    chip_row: sqlite3.Row,
    peripheral: str | None,
    register: str | None,
    address: int | None,
) -> tuple[sqlite3.Row, sqlite3.Row]:
    if address is not None:
        return resolve_register_by_address(conn, chip_row, address)
    if peripheral and register:
        return resolve_register_by_name(conn, chip_row, peripheral, register)
    raise ChipsageQueryError(
        "specify the register by 'peripheral' + 'register', or by absolute 'address'"
    )


# --- shared shaping ------------------------------------------------------------------------


def _provenance(chip_row: sqlite3.Row) -> dict:
    citation = (
        f"{chip_row['vendor']} {chip_row['name']} · SVD v{chip_row['svd_version']} "
        f"· {chip_row['svd_source']}"
    )
    return {
        "vendor": chip_row["vendor"],
        "chip": chip_row["name"],
        "svd_version": chip_row["svd_version"],
        "svd_source": chip_row["svd_source"],
        "citation": citation,
    }


def _field_specs(conn: sqlite3.Connection, register_id: int) -> list[FieldSpec]:
    return [
        FieldSpec(r["name"], r["bit_offset"], r["bit_width"], r["access"])
        for r in conn.execute(
            "SELECT name, bit_offset, bit_width, access FROM fields WHERE register_id = ?",
            (register_id,),
        )
    ]


def _field_enum_rows(conn: sqlite3.Connection, field_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT name, value, description, is_default FROM enums WHERE field_id = ? "
        "ORDER BY (value IS NULL), value",
        (field_id,),
    ).fetchall()


def _enum_name_for(rows: list[sqlite3.Row], value: int) -> str | None:
    """Resolve a numeric field value to its symbolic name (a default entry is the fallback)."""
    default = None
    for r in rows:
        if r["is_default"]:
            default = r["name"]
        elif r["value"] == value:
            return r["name"]
    return default


def _register_info(prow: sqlite3.Row, rrow: sqlite3.Row) -> dict:
    size = rrow["size"]
    address = prow["base_address"] + rrow["address_offset"]
    return {
        "peripheral": prow["name"],
        "register": rrow["name"],
        "address": _hex(address, 32),
        "address_offset": _hex(rrow["address_offset"], 16),
        "size_bits": size,
        "access": rrow["access"],
        "reset_value": _hex(rrow["reset_value"], size),
        "reset_mask": _hex(rrow["reset_mask"], size),
        "description": rrow["description"],
    }


# --- tools ---------------------------------------------------------------------------------


def lookup_register(conn: sqlite3.Connection, chip: str, peripheral: str, register: str) -> dict:
    """Return a register's address, fields, reset value and access — with provenance."""
    chip_row = resolve_chip_row(conn, chip)
    prow, rrow = resolve_register_by_name(conn, chip_row, peripheral, register)
    rows = conn.execute(
        "SELECT id, name, description, bit_offset, bit_width, access, reset_value "
        "FROM fields WHERE register_id = ? ORDER BY bit_offset DESC",
        (rrow["id"],),
    ).fetchall()
    fields = [
        {
            "name": r["name"],
            "bits": _bits_label(r["bit_offset"], r["bit_width"]),
            "bit_offset": r["bit_offset"],
            "bit_width": r["bit_width"],
            "access": r["access"],
            "reset_value": _hex(r["reset_value"], r["bit_width"]),
            "description": r["description"],
            "enumerated_values": [
                {"value": e["value"], "name": e["name"], "description": e["description"]}
                for e in _field_enum_rows(conn, r["id"])
            ],
        }
        for r in rows
    ]
    reg = _register_info(prow, rrow)
    prov = _provenance(chip_row)
    return {
        "peripheral": {
            "name": prow["name"],
            "base_address": _hex(prow["base_address"], 32),
            "derived_from": prow["derived_from"],
            "description": prow["description"],
        },
        "register": reg,
        "fields": fields,
        "provenance": prov,
        "citation": prov["citation"],
        "summary": (
            f"{chip_row['name']}.{prow['name']}.{rrow['name']} @ {reg['address']} "
            f"({reg['size_bits']}-bit {reg['access']}), reset {reg['reset_value']}, "
            f"{len(fields)} field(s) — {prov['citation']}"
        ),
    }


def decode_dump(
    conn: sqlite3.Connection,
    chip: str,
    value: int,
    peripheral: str | None = None,
    register: str | None = None,
    address: int | None = None,
) -> dict:
    """Decode a raw register value into its named fields — with provenance."""
    chip_row = resolve_chip_row(conn, chip)
    prow, rrow = _resolve(conn, chip_row, peripheral, register, address)
    size = rrow["size"]
    field_rows = conn.execute(
        "SELECT id, name, bit_offset, bit_width, access FROM fields WHERE register_id = ? "
        "ORDER BY bit_offset",
        (rrow["id"],),
    ).fetchall()
    specs = [
        FieldSpec(r["name"], r["bit_offset"], r["bit_width"], r["access"]) for r in field_rows
    ]
    enum_field_id = {r["name"]: r["id"] for r in field_rows}
    masked = value & size_mask(size)
    decoded = decode_fields(masked, specs)

    notes = []
    if value < 0:
        raise ChipsageQueryError(f"value {value} is negative")
    if (value >> size) != 0:
        notes.append(
            f"value {value:#x} exceeds the {size}-bit register; decoded the low {size} bits "
            f"({_hex(masked, size)})"
        )
    reserved_set = masked & undefined_mask(specs, size)

    fields = [
        {
            "name": fv.name,
            "bits": _bits_label(fv.bit_offset, fv.bit_width),
            "value": _hex(fv.value, fv.bit_width),
            "value_int": fv.value,
            "enum": _enum_name_for(_field_enum_rows(conn, enum_field_id[fv.name]), fv.value),
            "access": fv.access,
        }
        for fv in decoded
    ]
    prov = _provenance(chip_row)
    return {
        "register": _register_info(prow, rrow),
        "value": _hex(masked, size),
        "fields": fields,
        "reserved_bits_set": _hex(reserved_set, size) if reserved_set else None,
        "notes": notes,
        "provenance": prov,
        "citation": prov["citation"],
    }


def check_write(
    conn: sqlite3.Connection,
    chip: str,
    value: int,
    peripheral: str | None = None,
    register: str | None = None,
    address: int | None = None,
) -> dict:
    """Check whether writing ``value`` to a register is valid — with provenance."""
    chip_row = resolve_chip_row(conn, chip)
    prow, rrow = _resolve(conn, chip_row, peripheral, register, address)
    size = rrow["size"]
    specs = _field_specs(conn, rrow["id"])
    field_values, issues = analyze_write(value, size, rrow["access"], specs)

    fields = [
        {
            "name": fv.name,
            "bits": _bits_label(fv.bit_offset, fv.bit_width),
            "value": _hex(fv.value, fv.bit_width),
            "access": effective_access(fv.access, rrow["access"]),
        }
        for fv in field_values
    ]
    prov = _provenance(chip_row)
    return {
        "register": _register_info(prow, rrow),
        "value": _hex(value, size) if value >= 0 else str(value),
        "ok": not has_errors(issues),
        "issues": [
            {"severity": i.severity, "code": i.code, "message": i.message} for i in issues
        ],
        "fields": fields,
        "provenance": prov,
        "citation": prov["citation"],
    }
