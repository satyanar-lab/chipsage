"""Unit tests for the pure bit helpers (no database, no MCP)."""

from __future__ import annotations

from chipsage.bits import (
    FieldSpec,
    analyze_write,
    coverage_mask,
    decode_fields,
    effective_access,
    extract_field,
    has_errors,
    size_mask,
    undefined_mask,
)

# An 8-bit register: EN[0], MODE[2:1]; bits [7:3] are reserved.
EN = FieldSpec("EN", 0, 1, "read-write")
MODE = FieldSpec("MODE", 1, 2, "read-write")
LAYOUT = (EN, MODE)


def test_size_mask() -> None:
    assert size_mask(8) == 0xFF
    assert size_mask(32) == 0xFFFFFFFF


def test_extract_field() -> None:
    assert extract_field(0b101, 0, 1) == 1
    assert extract_field(0b101, 1, 2) == 0b10
    assert extract_field(0x20008147, 12, 16) == (0x20008147 >> 12) & 0xFFFF


def test_coverage_and_undefined_mask() -> None:
    assert coverage_mask(LAYOUT) == 0b111
    assert undefined_mask(LAYOUT, 8) == 0xF8


def test_decode_fields_orders_msb_first() -> None:
    decoded = decode_fields(0b101, LAYOUT)
    assert [fv.name for fv in decoded] == ["MODE", "EN"]  # MODE (bit 2:1) before EN (bit 0)
    values = {fv.name: fv.value for fv in decoded}
    assert values == {"EN": 1, "MODE": 0b10}


def test_effective_access_inherits_register() -> None:
    assert effective_access("read-only", "read-write") == "read-only"
    assert effective_access(None, "read-write") == "read-write"
    assert effective_access(None, None) is None


def test_analyze_write_clean() -> None:
    values, issues = analyze_write(0b101, 8, "read-write", LAYOUT)
    assert issues == []
    assert not has_errors(issues)
    assert {v.name: v.value for v in values} == {"EN": 1, "MODE": 0b10}


def test_analyze_write_overflow_is_error() -> None:
    _, issues = analyze_write(0x100, 8, "read-write", LAYOUT)
    assert has_errors(issues)
    assert [i.code for i in issues if i.severity == "error"] == ["value_overflow"]


def test_analyze_write_negative_is_error() -> None:
    values, issues = analyze_write(-1, 8, "read-write", LAYOUT)
    assert values == []
    assert [i.code for i in issues] == ["negative_value"]
    assert has_errors(issues)


def test_analyze_write_reserved_bits_warns() -> None:
    _, issues = analyze_write(0b1000, 8, "read-write", LAYOUT)  # bit 3 is reserved
    codes = [i.code for i in issues]
    assert "reserved_bits" in codes
    assert not has_errors(issues)  # a warning, not an error


def test_analyze_write_read_only_field_warns() -> None:
    stat = FieldSpec("STAT", 0, 1, "read-only")
    _, issues = analyze_write(0b1, 8, "read-write", (stat,))
    ro = [i for i in issues if i.code == "read_only_field"]
    assert len(ro) == 1
    assert ro[0].severity == "warning"
    # writing 0 into the same read-only field is fine
    _, issues0 = analyze_write(0b0, 8, "read-write", (stat,))
    assert issues0 == []


def test_analyze_write_write_once_note() -> None:
    wo = FieldSpec("KEY", 0, 4, "writeOnce")
    _, issues = analyze_write(0b1, 8, "read-write", (wo,))
    assert [i.code for i in issues] == ["write_once"]
    assert issues[0].severity == "note"


def test_analyze_write_read_only_register_note() -> None:
    _, issues = analyze_write(0, 8, "read-only", LAYOUT)
    assert any(i.code == "read_only_register" and i.severity == "note" for i in issues)
