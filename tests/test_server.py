"""Smoke tests for the MCP server: tool registration and an end-to-end call_tool round-trip."""

from __future__ import annotations

import json
from pathlib import Path

import anyio
import pytest

from chipsage import server


@pytest.fixture
def dbenv(monkeypatch: pytest.MonkeyPatch, built_db_path: Path) -> None:
    monkeypatch.setenv("CHIPSAGE_DB", str(built_db_path))


def _text(result: object) -> str:
    """Extract the text payload from a FastMCP call_tool result (list or (content, _) tuple)."""
    content = result[0] if isinstance(result, tuple) else result
    return content[0].text


def test_tool_functions_run_against_index(dbenv: None) -> None:
    r = server.lookup_register("RP2040", "SIO", "GPIO_OUT")
    assert r["register"]["address"] == "0xD0000010"
    assert "RP2040.svd" in r["citation"]

    d = server.decode_dump("RP2040", "0x01ffffff", peripheral="RESETS", register="RESET")
    assert len(d["fields"]) == 25

    w = server.check_write("RP2040", "0x100000000", peripheral="SIO", register="GPIO_OUT")
    assert w["ok"] is False


def test_hex_and_decimal_values_parse(dbenv: None) -> None:
    hexed = server.decode_dump("RP2040", "0x10", peripheral="ADC", register="CS")
    decimal = server.decode_dump("RP2040", "16", peripheral="ADC", register="CS")
    assert hexed["reserved_bits_set"] == decimal["reserved_bits_set"] == "0x00000010"


def test_three_tools_are_registered() -> None:
    tools = anyio.run(server.mcp.list_tools)
    assert {t.name for t in tools} == {"lookup_register", "decode_dump", "check_write"}
    lookup = next(t for t in tools if t.name == "lookup_register")
    assert {"chip", "peripheral", "register"} <= set(lookup.inputSchema["properties"])


def test_call_tool_roundtrip(dbenv: None) -> None:
    result = anyio.run(
        server.mcp.call_tool,
        "lookup_register",
        {"chip": "RP2040", "peripheral": "SIO", "register": "GPIO_OUT"},
    )
    payload = json.loads(_text(result))
    assert payload["register"]["address"] == "0xD0000010"
    assert "RP2040.svd" in payload["citation"]


def test_main_errors_when_index_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("CHIPSAGE_DB", raising=False)
    with pytest.raises(SystemExit):
        server.main(["--db", str(tmp_path / "does-not-exist.db")])


def test_decode_tool_resolves_enum(dbenv: None) -> None:
    d = server.decode_dump("RP2040", "0x2", peripheral="CLOCKS", register="CLK_REF_CTRL")
    src = next(f for f in d["fields"] if f["name"] == "SRC")
    assert src["enum"] == "xosc_clksrc"
