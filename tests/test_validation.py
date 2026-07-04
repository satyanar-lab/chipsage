"""Unit tests for the pure Tier-1 validators (no database involved)."""

from __future__ import annotations

import pytest

from chipsage.models import AddressBlock, EnumeratedValue, Field, Peripheral, Register
from chipsage.validation import (
    SCOPE_ENUM,
    SCOPE_FIELD,
    SCOPE_REGISTER,
    find_overlapping_fields,
    reset_value_fits,
    validate_enum,
    validate_field,
    validate_register,
)


def _peripheral(*registers: Register, block_size: int = 0x100) -> Peripheral:
    return Peripheral(
        name="P",
        base_address=0x4000_0000,
        address_blocks=(AddressBlock(0, block_size),),
        registers=registers,
    )


# --- reset_value_fits ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "width", "expected"),
    [
        (0, 1, True),
        (1, 1, True),
        (2, 1, False),  # 0b10 needs 2 bits
        (7, 3, True),
        (8, 3, False),
        (0xFFFF_FFFF, 32, True),
        (0x1_0000_0000, 32, False),
        (-1, 8, False),  # negatives never fit
    ],
)
def test_reset_value_fits(value: int, width: int, expected: bool) -> None:
    assert reset_value_fits(value, width) is expected


# --- find_overlapping_fields --------------------------------------------------------------


def test_no_overlap_for_adjacent_fields() -> None:
    fields = (Field("A", 0, 4), Field("B", 4, 4), Field("C", 8, 1))
    assert find_overlapping_fields(fields) == []


def test_overlap_detected_for_neighbours() -> None:
    fields = (Field("A", 0, 4), Field("B", 2, 4))  # [0,4) vs [2,6)
    assert find_overlapping_fields(fields) == [("A", "B")]


def test_overlap_detected_for_non_adjacent_fields() -> None:
    # A wide field swallows two later narrow ones; sorting-by-offset + neighbour-only checks
    # would miss the A/C pair — the sweep must catch it.
    fields = (Field("WIDE", 0, 20), Field("B", 4, 2), Field("C", 8, 2))
    overlaps = find_overlapping_fields(fields)
    assert ("WIDE", "B") in overlaps
    assert ("WIDE", "C") in overlaps


def test_overlap_is_order_independent() -> None:
    forward = find_overlapping_fields((Field("A", 0, 4), Field("B", 2, 4)))
    reverse = find_overlapping_fields((Field("B", 2, 4), Field("A", 0, 4)))
    assert forward == reverse == [("A", "B")]


# --- validate_field -----------------------------------------------------------------------


def test_valid_field_has_no_violations() -> None:
    reg = Register("R", 0, 32, fields=(Field("EN", 0, 1, reset_value=1),))
    assert validate_field(reg.fields[0], reg, _peripheral(reg)) == []


def test_field_beyond_register_width_rejected() -> None:
    reg = Register("R", 0, 8)  # 8-bit register
    fld = Field("TOOBIG", 4, 8)  # occupies bits [4,12) -> exceeds 8
    violations = validate_field(fld, reg, _peripheral(reg))
    assert [v.rule for v in violations] == ["field_out_of_range"]
    assert violations[0].scope == SCOPE_FIELD
    assert violations[0].field == "TOOBIG"


def test_field_negative_offset_rejected() -> None:
    reg = Register("R", 0, 32)
    violations = validate_field(Field("BAD", -1, 4), reg, _peripheral(reg))
    assert any(v.rule == "field_out_of_range" for v in violations)


def test_field_zero_width_rejected() -> None:
    reg = Register("R", 0, 32)
    violations = validate_field(Field("ZERO", 0, 0), reg, _peripheral(reg))
    assert any(v.rule == "field_width" for v in violations)


def test_field_reset_overflow_rejected() -> None:
    reg = Register("R", 0, 32)
    fld = Field("F", 0, 3, reset_value=8)  # 8 does not fit in 3 bits
    violations = validate_field(fld, reg, _peripheral(reg))
    assert [v.rule for v in violations] == ["reset_overflow"]


# --- validate_register --------------------------------------------------------------------


def test_valid_register_has_no_violations() -> None:
    reg = Register("R", 0x04, 32, reset_value=0x1, fields=(Field("A", 0, 1), Field("B", 1, 1)))
    assert validate_register(reg, _peripheral(reg)) == []


def test_register_address_out_of_range_rejected() -> None:
    reg = Register("R", 0x200, 32)  # 0x200 is past the 0x100-byte block
    violations = validate_register(reg, _peripheral(reg, block_size=0x100))
    assert [v.rule for v in violations] == ["address_out_of_range"]
    assert violations[0].scope == SCOPE_REGISTER


def test_register_within_range_ok() -> None:
    reg = Register("R", 0xFC, 32)  # [0xFC, 0x100) fits exactly in a 0x100 block
    assert validate_register(reg, _peripheral(reg, block_size=0x100)) == []


def test_register_straddling_block_end_rejected() -> None:
    reg = Register("R", 0xFE, 32)  # [0xFE, 0x102) spills past a 0x100 block
    violations = validate_register(reg, _peripheral(reg, block_size=0x100))
    assert [v.rule for v in violations] == ["address_out_of_range"]


def test_register_reset_overflow_rejected() -> None:
    reg = Register("R", 0x00, 8, reset_value=0x1FF)  # 0x1FF needs 9 bits
    violations = validate_register(reg, _peripheral(reg))
    assert [v.rule for v in violations] == ["reset_overflow"]


def test_register_overlapping_fields_rejected() -> None:
    reg = Register("R", 0x00, 32, fields=(Field("A", 0, 4), Field("B", 2, 4)))
    violations = validate_register(reg, _peripheral(reg))
    assert [v.rule for v in violations] == ["field_overlap"]
    assert violations[0].scope == SCOPE_REGISTER


def test_register_with_no_address_blocks_skips_range_check() -> None:
    # Cannot verify a range that was never declared: skip rather than guess.
    reg = Register("R", 0xFFFF, 32)
    peripheral = Peripheral(name="P", base_address=0, address_blocks=(), registers=(reg,))
    assert validate_register(reg, peripheral) == []


# --- validate_enum ------------------------------------------------------------------------


def test_enum_value_within_field_width_ok() -> None:
    fld = Field("MODE", 0, 2)  # 2-bit field, max value 3
    reg = Register("R", 0x00, 32, fields=(fld,))
    assert validate_enum(EnumeratedValue("full", 3), fld, _peripheral(reg), reg) == []


def test_enum_value_too_wide_rejected() -> None:
    fld = Field("MODE", 0, 2)
    reg = Register("R", 0x00, 32, fields=(fld,))
    violations = validate_enum(EnumeratedValue("bad", 4), fld, _peripheral(reg), reg)
    assert [v.rule for v in violations] == ["enum_out_of_range"]
    assert violations[0].scope == SCOPE_ENUM
    assert violations[0].field == "MODE"


def test_enum_default_entry_exempt() -> None:
    fld = Field("MODE", 0, 2)
    reg = Register("R", 0x00, 32, fields=(fld,))
    default = EnumeratedValue("other", None, is_default=True)
    assert validate_enum(default, fld, _peripheral(reg), reg) == []
