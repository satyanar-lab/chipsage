# chipsage

[![CI](https://github.com/satyanar-lab/chipsage/actions/workflows/ci.yml/badge.svg)](https://github.com/satyanar-lab/chipsage/actions/workflows/ci.yml)

**A local, zero-cost MCP server that gives AI coding tools hallucination-free,
citation-backed access to microcontroller documentation.**

AI reasons; chipsage verifies. Nothing enters the index without ground truth, and nothing
leaves a tool without a source reference. Register facts are parsed straight from vendor
CMSIS-SVD files and validated at ingest — they are *exact by construction*, not
model-generated.

> **Development disclosure.** chipsage is built through AI-directed development using
> [Claude Code](https://www.anthropic.com/claude-code). The AI writes and refactors the
> code; the architecture (see [`CLAUDE.md`](CLAUDE.md)) forbids the model from ever
> *originating* a hardware value — every stored fact traces back to a vendor source.

---

## Status

Built in phases. **Phases 1–2.5 are complete; later phases are not yet started.**

| Phase | Scope | State |
|------:|-------|-------|
| **1** | Repo scaffold, `pyproject`, SVD→SQLite loader + ingest validation, proven against RP2040 & RP2350 | ✅ done |
| **2** | MCP server (stdio) + `lookup_register`, `decode_dump`, `check_write` | ✅ done |
| **2.5** | SVD enumerated values in the index, surfaced by `decode_dump` + `lookup_register` | ✅ done |
| 3 | FTS5 prose/errata indexer + `get_errata` join | ⬜ planned |
| 4 | Camelot Tier-2 electrical/timing tables + provenance gate | ⬜ planned |
| 5 | Eval harness, CI badge, demo, packaged release with pre-built index | ⬜ planned |

## Trust tiers

chipsage classifies every fact by how it was obtained:

- **Tier 1 — Registers (this phase).** Parsed from vendor CMSIS-SVD via the `cmsis-svd`
  package into SQLite. Validated at ingest: no overlapping fields, register addresses within
  the peripheral's declared address blocks, reset values that fit their widths. Violations
  are **rejected and logged, never silently repaired.**
- **Tier 2 — Electrical/timing tables (later).** Extracted from datasheet PDFs with a
  provenance gate: a numeric cell is kept only if it appears verbatim on its cited page.
- **Tier 3 — Prose/errata (later).** Page-anchored full-text search; tools return excerpts
  with page numbers and never paraphrase.

## What Phase 1 gives you

A single, vendor-agnostic SQLite index keyed by `(vendor, chip, peripheral, register,
field)`, built from the vendored SVDs, with provenance (`svd_version`, `svd_source`) on
every chip. From the pinned files that ships as:

- **RP2040** — 37 peripherals, ~1.2k registers, ~5.8k fields
- **RP2350** — 54 peripherals, ~3.0k registers, ~12.2k fields

(Exact inserted counts are printed by `chipsage-build`.)

## Quickstart

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# quality gates
.venv/bin/ruff check .
.venv/bin/pytest

# build the Tier-1 index from the vendored SVDs
.venv/bin/chipsage-build --svd data/svd/RP2040.svd data/svd/RP2350.svd -o chipsage.db --strict

# run the MCP server (stdio) against that index
.venv/bin/chipsage-mcp --db chipsage.db
```

The loader reads local files only — **no network at build or runtime.** To reproduce or
refresh the vendored SVDs from upstream (and verify their pinned SHA-256), see
[`data/svd/SOURCES.md`](data/svd/SOURCES.md) and `scripts/fetch_svds.py`.

## MCP tools (Phase 2)

The server speaks MCP over **stdio** and exposes three deterministic, read-only,
citation-backed tools. Every response includes a `provenance` block and a `citation` string
(vendor · chip · SVD version · source file) — nothing is paraphrased or inferred.

| Tool | What it does |
|------|--------------|
| `lookup_register` | Address, size, access, reset value/mask and the full field map for a register (by `chip` + `peripheral` + `register`, case-insensitive), including each field's **enumerated values** (symbolic name ↔ number). |
| `decode_dump` | Decodes a raw register `value` into its named fields — each with its numeric value **and symbolic enum name** where the SVD defines one (e.g. `SRC=2 (xosc_clksrc)`). Identify the register by name or by absolute `address` (e.g. from a debugger dump). Flags any reserved bits that are set. |
| `check_write` | Checks whether writing `value` is valid: values wider than the register (error), reserved/undefined bits (warning) and non-zero writes into read-only fields (warning). Returns `ok` plus an issue list. |

`value` and `address` accept hex (`0x...`) or decimal.

## Install as MCP server

Build an index at a **stable absolute location** first. MCP clients launch the server from an
arbitrary working directory, so a bare `chipsage.db` (resolved against the client's cwd) will
not be found — always pass an absolute `--db`, and an absolute path to the `chipsage-mcp`
binary.

```bash
.venv/bin/chipsage-build --svd data/svd/RP2040.svd data/svd/RP2350.svd -o "$PWD/chipsage.db" --strict
```

**Claude Code** — one command (substitute your checkout path for `/ABS/chipsage`; run `pwd`
in the repo to get it):

```bash
claude mcp add chipsage -- \
  /ABS/chipsage/.venv/bin/chipsage-mcp --db /ABS/chipsage/chipsage.db
```

The `--` separates chipsage's flags from `claude`'s own. Add `--scope user` before the name
to make it available in every project. Verify with `claude mcp get chipsage` — it should
report `✔ Connected`.

**Claude Desktop** — add to `claude_desktop_config.json` (macOS
`~/Library/Application Support/Claude/`, Windows `%APPDATA%\Claude\`), then restart the app:

```json
{
  "mcpServers": {
    "chipsage": {
      "command": "/ABS/chipsage/.venv/bin/chipsage-mcp",
      "args": ["--db", "/ABS/chipsage/chipsage.db"]
    }
  }
}
```

### How the server finds the index

In priority order: the `--db PATH` flag → the `CHIPSAGE_DB` environment variable → a default
of `chipsage.db` **relative to the current directory**. Because MCP clients start the server
from an unpredictable cwd, the cwd-relative default is unreliable for real installs — **bake
an absolute `--db` into the command above.** If the index is missing, the server exits
immediately with `index not found: <path>`. It opens the index **read-only** and makes **no
network calls** — a tool can only read the prebuilt SQLite file.

### Try it

Once connected, ask in natural language — chipsage answers with a source citation:

```
You:      What is the reset value of the RP2040 SYSINFO CHIP_ID register?
chipsage: CHIP_ID @ 0x40000000 resets to 0x20002927 (32-bit, read-write)
          — cited: Raspberry Pi RP2040 · SVD v0.1 · RP2040.svd

You:      Decode RP2040 CLOCKS CLK_REF_CTRL = 0x2
chipsage: SRC = 2 (xosc_clksrc), AUXSRC = 0 (clksrc_pll_usb)
          — cited: Raspberry Pi RP2040 · SVD v0.1 · RP2040.svd
```

## Layout

```
src/chipsage/
  models.py       vendor-agnostic domain model (frozen dataclasses)
  svd.py          the ONLY module that imports cmsis_svd; SVD -> model
  validation.py   pure Tier-1 validators (+ Violation)
  schema.py       SQLite DDL + schema version
  db.py           connection helpers
  loader.py       validate + insert; rejects-and-logs, returns a LoadReport
  build_index.py  the `chipsage-build` CLI
  bits.py         pure bit math for decode/check (no DB, no MCP)
  query.py        citation-backed query layer over the index
  server.py       the `chipsage-mcp` FastMCP stdio server (3 tools)
data/svd/         vendored ground-truth SVDs + SOURCES.md (URLs, licence, sha256)
tests/            pure (validators, bits) + DB-backed (loader, query) + MCP server tests
```

## Scope & limitations

- **Registers only.** The tools cover Tier-1 registers, including SVD *enumerated values*
  (symbolic field-value names). No electrical/timing tables, prose, or errata yet (Tiers 2–3
  are later phases).
- **Two chips.** Only RP2040 and RP2350 are indexed. STM32 (H753, L152) and ESP32 follow,
  per the vendor order in the Constitution.
- **Only as good as the SVD.** Tier-1 accuracy is exactly the accuracy of the vendor SVD.
  The RP2040/RP2350 SVDs from pico-sdk are first-party and load with **zero** validation
  violations. Community SVDs (notably ESP32, later) vary in quality; chipsage's ingest
  validation exists precisely to reject — and loudly log — inconsistent entries rather than
  serve them.

## Licence

chipsage is licensed under the [MIT Licence](LICENSE). The vendored SVD files under
`data/svd/` retain their upstream **BSD-3-Clause** licence from the Raspberry Pi pico-sdk;
see [`data/svd/SOURCES.md`](data/svd/SOURCES.md).
