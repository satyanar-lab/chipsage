"""Tier-1 ingest validators.

The Constitution requires the loader to validate at ingest — *"no overlapping fields,
addresses within peripheral ranges, reset values fit field widths. Reject and log
violations; never silently repair."*

These functions are pure: no I/O, no mutation. They inspect the domain model and return a
list of :class:`Violation`. Each violation has a ``scope`` that tells the loader how much to
reject:

* ``SCOPE_REGISTER`` — the register's integrity is compromised (address out of range, reset
  value too wide for the register, or overlapping fields). The whole register and its fields
  are rejected. Overlaps reject the register rather than guess which of two conflicting
  fields is authoritative — better to omit than to serve an internally inconsistent map.
* ``SCOPE_FIELD`` — only the offending field is rejected; the rest of the register stands.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Field, Peripheral, Register

SCOPE_REGISTER = "register"
SCOPE_FIELD = "field"


@dataclass(frozen=True)
class Violation:
    """A single rejected entity, with enough context to log and audit it."""

    rule: str  # machine-readable rule id, e.g. "field_overlap"
    scope: str  # SCOPE_REGISTER or SCOPE_FIELD
    peripheral: str
    register: str
    detail: str  # human-readable explanation
    field: str | None = None

    def __str__(self) -> str:
        location = f"{self.peripheral}.{self.register}"
        if self.field:
            location = f"{location}.{self.field}"
        return f"[{self.rule}] {location}: {self.detail}"


def reset_value_fits(value: int, width_bits: int) -> bool:
    """True if ``value`` is a non-negative integer representable in ``width_bits`` bits."""
    if value < 0:
        return False
    return (value >> width_bits) == 0


def find_overlapping_fields(fields: tuple[Field, ...]) -> list[tuple[str, str]]:
    """Return ``(a, b)`` name pairs of fields whose bit ranges overlap.

    Uses a sweep over fields sorted by offset, tracking the furthest bit reached so far, so
    it catches overlaps between non-adjacent fields (e.g. a wide field that swallows a later
    narrow one), not just neighbours.
    """
    ordered = sorted(fields, key=lambda f: f.bit_offset)
    overlaps: list[tuple[str, str]] = []
    max_end = -1
    max_field: Field | None = None
    for f in ordered:
        if max_field is not None and f.bit_offset < max_end:
            overlaps.append((max_field.name, f.name))
        end = f.bit_offset + f.bit_width
        if end > max_end:
            max_end = end
            max_field = f
    return overlaps


def validate_field(field: Field, register: Register, peripheral: Peripheral) -> list[Violation]:
    """Validate a single field against its register. Returns field-scope violations."""
    problems: list[Violation] = []

    def add(rule: str, detail: str) -> None:
        problems.append(
            Violation(rule, SCOPE_FIELD, peripheral.name, register.name, detail, field.name)
        )

    if field.bit_width < 1:
        add("field_width", f"bit_width {field.bit_width} must be >= 1")
    if field.bit_offset < 0:
        add("field_out_of_range", f"bit_offset {field.bit_offset} is negative")
    elif field.bit_width >= 1 and field.bit_offset + field.bit_width > register.size:
        add(
            "field_out_of_range",
            f"bits [{field.bit_offset}:{field.msb}] exceed the {register.size}-bit register",
        )
    if field.reset_value is not None and not reset_value_fits(field.reset_value, field.bit_width):
        add(
            "reset_overflow",
            f"reset value {field.reset_value:#x} does not fit in {field.bit_width} bit(s)",
        )
    return problems


def validate_register(register: Register, peripheral: Peripheral) -> list[Violation]:
    """Validate a register against its peripheral. Returns register-scope violations."""
    problems: list[Violation] = []

    def add(rule: str, detail: str) -> None:
        problems.append(Violation(rule, SCOPE_REGISTER, peripheral.name, register.name, detail))

    # Address within a declared peripheral range. When the peripheral declares no address
    # blocks the range cannot be verified, so the check is skipped rather than guessed.
    if register.address_offset < 0:
        add("address_out_of_range", f"address_offset {register.address_offset:#x} is negative")
    elif peripheral.address_blocks:
        end = register.address_offset + register.size_bytes
        within = any(
            block.offset <= register.address_offset and end <= block.offset + block.size
            for block in peripheral.address_blocks
        )
        if not within:
            add(
                "address_out_of_range",
                f"[{register.address_offset:#x}..{end:#x}) is outside the peripheral's "
                f"address block(s) {[(b.offset, b.size) for b in peripheral.address_blocks]}",
            )

    # Reset value must fit the register width.
    reset = register.reset_value
    if reset is not None and not reset_value_fits(reset, register.size):
        add("reset_overflow", f"reset value {reset:#x} does not fit in {register.size} bit(s)")

    # No overlapping fields.
    for a, b in find_overlapping_fields(register.fields):
        add("field_overlap", f"fields {a!r} and {b!r} overlap")

    return problems
