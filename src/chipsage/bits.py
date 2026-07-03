"""Pure bit-level helpers for decoding register values and analysing writes.

No database, no MCP, no I/O — just integer math over field layouts. These functions are the
computational core of ``decode_dump`` and ``check_write``, kept pure so every branch is
unit-tested directly. They never originate a hardware fact; they only rearrange the bits of a
value the caller supplies against a field layout that came from the SVD-backed index.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

# SVD access strings (the canonical values emitted by cmsis-svd's SVDAccessType).
READ_ONLY = "read-only"
WRITE_ONLY = "write-only"
READ_WRITE = "read-write"
WRITE_ONCE = "writeOnce"
READ_WRITE_ONCE = "read-writeOnce"


@dataclass(frozen=True)
class FieldSpec:
    """Minimal field layout used by the bit helpers (decoupled from the DB row / model)."""

    name: str
    bit_offset: int
    bit_width: int
    access: str | None = None

    @property
    def mask(self) -> int:
        return ((1 << self.bit_width) - 1) << self.bit_offset


@dataclass(frozen=True)
class FieldValue:
    """A field's decoded value within a register word."""

    name: str
    bit_offset: int
    bit_width: int
    value: int
    access: str | None = None

    @property
    def msb(self) -> int:
        return self.bit_offset + self.bit_width - 1


@dataclass(frozen=True)
class WriteIssue:
    """One finding from :func:`analyze_write`."""

    severity: str  # "error" | "warning" | "note"
    code: str
    message: str


def size_mask(size_bits: int) -> int:
    """All-ones mask ``size_bits`` wide."""
    return (1 << size_bits) - 1


def extract_field(value: int, bit_offset: int, bit_width: int) -> int:
    """Extract the ``bit_width`` bits at ``bit_offset`` from ``value``."""
    return (value >> bit_offset) & ((1 << bit_width) - 1)


def coverage_mask(fields: Iterable[FieldSpec]) -> int:
    """Bitmask of every bit covered by at least one field."""
    mask = 0
    for f in fields:
        mask |= ((1 << f.bit_width) - 1) << f.bit_offset
    return mask


def undefined_mask(fields: Iterable[FieldSpec], size_bits: int) -> int:
    """Bits within the register width not covered by any field (reserved/undefined)."""
    return size_mask(size_bits) & ~coverage_mask(fields)


def decode_fields(value: int, fields: Iterable[FieldSpec]) -> list[FieldValue]:
    """Decode ``value`` into per-field values, ordered most-significant field first."""
    decoded = [
        FieldValue(f.name, f.bit_offset, f.bit_width,
                   extract_field(value, f.bit_offset, f.bit_width), f.access)
        for f in fields
    ]
    decoded.sort(key=lambda fv: fv.bit_offset, reverse=True)
    return decoded


def effective_access(field_access: str | None, register_access: str | None) -> str | None:
    """SVD rule: a field inherits the register's access when it declares none."""
    return field_access or register_access


def analyze_write(
    value: int,
    size_bits: int,
    register_access: str | None,
    fields: Iterable[FieldSpec],
) -> tuple[list[FieldValue], list[WriteIssue]]:
    """Analyse writing ``value`` into a register.

    Returns ``(field_values, issues)``. Issue codes:

    * ``error   negative_value``   — value is negative
    * ``error   value_overflow``   — value has bits beyond the register width
    * ``warning reserved_bits``    — sets bits not covered by any field
    * ``warning read_only_field``  — writes a non-zero value into a read-only field
    * ``note    read_only_register`` — the whole register is read-only
    * ``note    write_once``       — writes a write-once field
    """
    fields = list(fields)
    issues: list[WriteIssue] = []

    if value < 0:
        issues.append(WriteIssue("error", "negative_value", f"value {value} is negative"))
        return [], issues

    if (value >> size_bits) != 0:
        issues.append(WriteIssue(
            "error", "value_overflow",
            f"value {value:#x} exceeds the {size_bits}-bit register "
            f"(max {size_mask(size_bits):#x})",
        ))

    masked = value & size_mask(size_bits)
    field_values = decode_fields(masked, fields)

    reserved_set = masked & undefined_mask(fields, size_bits)
    if reserved_set:
        issues.append(WriteIssue(
            "warning", "reserved_bits",
            f"sets reserved/undefined bits {reserved_set:#x}",
        ))

    if register_access == READ_ONLY:
        issues.append(WriteIssue(
            "note", "read_only_register",
            "register access is read-only; the write may be ignored by hardware",
        ))

    for fv in field_values:
        if fv.value == 0:
            continue
        access = effective_access(fv.access, register_access)
        if access == READ_ONLY:
            issues.append(WriteIssue(
                "warning", "read_only_field",
                f"writes {fv.value:#x} into read-only field {fv.name!r} "
                f"[{fv.msb}:{fv.bit_offset}]",
            ))
        elif access in (WRITE_ONCE, READ_WRITE_ONCE):
            issues.append(WriteIssue(
                "note", "write_once",
                f"field {fv.name!r} is {access}: writable only once after reset",
            ))

    return field_values, issues


def has_errors(issues: Iterable[WriteIssue]) -> bool:
    """True if any issue is an error (writes with only warnings/notes are still 'ok')."""
    return any(i.severity == "error" for i in issues)
