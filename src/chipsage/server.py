"""chipsage MCP server (stdio transport) — Tier-1 register tools.

Exposes three deterministic, citation-backed tools over stdio: ``lookup_register``,
``decode_dump`` and ``check_write``. The server is strictly read-only — it opens a prebuilt
SQLite index in ``mode=ro`` and makes no network calls — so nothing a tool does can mutate
the index or reach outside the machine.

Point it at an index with ``--db PATH`` or the ``CHIPSAGE_DB`` environment variable
(default ``chipsage.db``). Build one first with ``chipsage-build``.
"""

from __future__ import annotations

import argparse
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import query
from .db import connect_ro

mcp = FastMCP("chipsage")

DEFAULT_DB = "chipsage.db"


def _db_path() -> str:
    return os.environ.get("CHIPSAGE_DB", DEFAULT_DB)


def _parse_int(text: str, label: str) -> int:
    """Parse an integer written in hex (``0x..``), decimal, octal or binary (base 0)."""
    try:
        return int(str(text), 0)
    except (TypeError, ValueError):
        raise query.ChipsageQueryError(
            f"{label} {text!r} is not a valid integer (use 0x-hex or decimal)"
        ) from None


def _run(fn, **kwargs) -> dict[str, Any]:
    conn = connect_ro(_db_path())
    try:
        return fn(conn, **kwargs)
    finally:
        conn.close()


@mcp.tool()
def lookup_register(chip: str, peripheral: str, register: str) -> dict[str, Any]:
    """Look up one microcontroller register from the SVD-backed index.

    Returns its absolute address, size, access, reset value/mask, and the full field map
    (bit ranges, per-field access and reset), plus provenance (vendor, chip, SVD version and
    source file). Names are case-insensitive. Example: chip="RP2040", peripheral="SIO",
    register="GPIO_OUT".
    """
    return _run(query.lookup_register, chip=chip, peripheral=peripheral, register=register)


@mcp.tool()
def decode_dump(
    chip: str,
    value: str,
    peripheral: str | None = None,
    register: str | None = None,
    address: str | None = None,
) -> dict[str, Any]:
    """Decode a raw register value into its named fields.

    Identify the register either by ``peripheral`` + ``register`` name, or by absolute
    ``address`` (e.g. from a debugger/memory dump). ``value`` and ``address`` accept hex
    (``0x...``) or decimal. Reports each field's decoded value and flags any reserved bits
    that are set. Carries provenance. Example: chip="RP2040", peripheral="RESETS",
    register="RESET", value="0x01ffffff".
    """
    return _run(
        query.decode_dump,
        chip=chip,
        value=_parse_int(value, "value"),
        peripheral=peripheral,
        register=register,
        address=_parse_int(address, "address") if address is not None else None,
    )


@mcp.tool()
def check_write(
    chip: str,
    value: str,
    peripheral: str | None = None,
    register: str | None = None,
    address: str | None = None,
) -> dict[str, Any]:
    """Check whether writing ``value`` to a register is valid before you do it.

    Identify the register by ``peripheral`` + ``register`` name or by absolute ``address``.
    Flags: values wider than the register, bits set in reserved/undefined positions, and
    non-zero writes into read-only fields. Returns ``ok`` plus a list of issues
    (error/warning/note) and the per-field breakdown, with provenance. ``value``/``address``
    accept hex or decimal.
    """
    return _run(
        query.check_write,
        chip=chip,
        value=_parse_int(value, "value"),
        peripheral=peripheral,
        register=register,
        address=_parse_int(address, "address") if address is not None else None,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="chipsage-mcp",
        description="chipsage MCP server (stdio) exposing Tier-1 register tools.",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="path to the chipsage SQLite index (default: $CHIPSAGE_DB or chipsage.db)",
    )
    args = parser.parse_args(argv)
    if args.db:
        os.environ["CHIPSAGE_DB"] = args.db

    path = _db_path()
    if not os.path.exists(path):
        parser.error(
            f"index not found: {path} — build it with `chipsage-build` "
            f"or pass --db / set CHIPSAGE_DB"
        )

    mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
