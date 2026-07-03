"""DB-backed tests for the citation-carrying query layer, against the real indexed SVDs."""

from __future__ import annotations

import sqlite3

import pytest

from chipsage.query import (
    ChipsageQueryError,
    check_write,
    decode_dump,
    lookup_register,
)

# --- lookup_register ----------------------------------------------------------------------


def test_lookup_sio_gpio_out(qconn: sqlite3.Connection) -> None:
    r = lookup_register(qconn, "RP2040", "SIO", "GPIO_OUT")
    assert r["register"]["address"] == "0xD0000010"
    assert r["register"]["size_bits"] == 32
    assert r["register"]["access"] == "read-write"
    assert r["register"]["reset_value"] == "0x00000000"
    assert [f["name"] for f in r["fields"]] == ["GPIO_OUT"]
    assert r["fields"][0]["bits"] == "[29:0]"


def test_lookup_carries_provenance(qconn: sqlite3.Connection) -> None:
    r = lookup_register(qconn, "RP2040", "SYSINFO", "CHIP_ID")
    prov = r["provenance"]
    assert prov["vendor"] == "Raspberry Pi"
    assert prov["chip"] == "RP2040"
    assert prov["svd_version"] == "0.1"
    assert prov["svd_source"] == "RP2040.svd"
    assert "RP2040.svd" in r["citation"]
    assert r["register"]["reset_value"] == "0x20002927"  # 536881447


def test_lookup_is_case_insensitive(qconn: sqlite3.Connection) -> None:
    r = lookup_register(qconn, "rp2040", "sio", "gpio_out")
    assert r["register"]["register"] == "GPIO_OUT"
    assert r["peripheral"]["name"] == "SIO"


def test_lookup_unknown_register_suggests(qconn: sqlite3.Connection) -> None:
    with pytest.raises(ChipsageQueryError) as excinfo:
        lookup_register(qconn, "RP2040", "SIO", "GPIO_OUUT")
    msg = str(excinfo.value).lower()
    assert "gpio_out" in msg  # a close match is suggested


def test_lookup_unknown_chip_lists_available(qconn: sqlite3.Connection) -> None:
    with pytest.raises(ChipsageQueryError) as excinfo:
        lookup_register(qconn, "RP9999", "SIO", "GPIO_OUT")
    assert "RP2040" in str(excinfo.value)


# --- decode_dump --------------------------------------------------------------------------


def test_decode_resets_reset_all_blocks(qconn: sqlite3.Connection) -> None:
    r = decode_dump(qconn, "RP2040", 0x01FFFFFF, peripheral="RESETS", register="RESET")
    assert r["register"]["register"] == "RESET"
    assert len(r["fields"]) == 25
    assert all(f["value"] == "0x1" for f in r["fields"])
    assert r["reserved_bits_set"] is None
    assert "RP2040.svd" in r["citation"]


def test_decode_by_absolute_address(qconn: sqlite3.Connection) -> None:
    r = decode_dump(qconn, "RP2040", 0x5, address=0xD0000010)
    assert r["register"]["peripheral"] == "SIO"
    assert r["register"]["register"] == "GPIO_OUT"
    assert r["fields"][0]["name"] == "GPIO_OUT"
    assert r["fields"][0]["value_int"] == 5


def test_decode_flags_reserved_bits(qconn: sqlite3.Connection) -> None:
    # ADC.CS has reserved bits 0xffe088f0; bit 4 is reserved.
    r = decode_dump(qconn, "RP2040", 0x10, peripheral="ADC", register="CS")
    assert r["reserved_bits_set"] == "0x00000010"


def test_decode_value_wider_than_register_is_masked_with_note(qconn: sqlite3.Connection) -> None:
    r = decode_dump(qconn, "RP2040", 0x1_0000_0005, peripheral="SIO", register="GPIO_OUT")
    assert r["value"] == "0x00000005"
    assert r["notes"] and "exceeds" in r["notes"][0]


def test_decode_address_not_in_any_peripheral(qconn: sqlite3.Connection) -> None:
    with pytest.raises(ChipsageQueryError):
        decode_dump(qconn, "RP2040", 0x0, address=0x3000_0000)


def test_decode_requires_a_target(qconn: sqlite3.Connection) -> None:
    with pytest.raises(ChipsageQueryError):
        decode_dump(qconn, "RP2040", 0x1)  # neither name nor address


# --- check_write --------------------------------------------------------------------------


def test_check_write_valid(qconn: sqlite3.Connection) -> None:
    r = check_write(qconn, "RP2040", 0x5, peripheral="SIO", register="GPIO_OUT")
    assert r["ok"] is True
    assert r["issues"] == []


def test_check_write_value_overflow_errors(qconn: sqlite3.Connection) -> None:
    r = check_write(qconn, "RP2040", 0x1_0000_0000, peripheral="SIO", register="GPIO_OUT")
    assert r["ok"] is False
    assert any(i["code"] == "value_overflow" for i in r["issues"])


def test_check_write_read_only_field_warns_but_ok(qconn: sqlite3.Connection) -> None:
    # SIO.GPIO_IN field GPIO_IN [29:0] is read-only (register is read-write).
    r = check_write(qconn, "RP2040", 0x1, peripheral="SIO", register="GPIO_IN")
    assert r["ok"] is True  # a warning, not an error
    assert any(i["code"] == "read_only_field" for i in r["issues"])


def test_check_write_reserved_bits_warns(qconn: sqlite3.Connection) -> None:
    r = check_write(qconn, "RP2040", 0x10, peripheral="ADC", register="CS")
    assert any(i["code"] == "reserved_bits" for i in r["issues"])


# --- cross-chip -------------------------------------------------------------------------


def test_rp2350_register_and_provenance(qconn: sqlite3.Connection) -> None:
    r = lookup_register(qconn, "RP2350", "SIO", "GPIO_OUT")
    assert r["provenance"]["svd_source"] == "RP2350.svd"
    assert r["fields"][0]["bits"] == "[31:0]"  # RP2350 widened the low GPIO bank
