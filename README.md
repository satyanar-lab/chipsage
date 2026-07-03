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

Built in phases. **Phase 1 is complete; later phases are not yet started.**

| Phase | Scope | State |
|------:|-------|-------|
| **1** | Repo scaffold, `pyproject`, SVD→SQLite loader + ingest validation, proven against RP2040 & RP2350 | ✅ done |
| 2 | MCP server + `lookup_register`, `decode_dump`, `check_write` | ⬜ planned |
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
```

The loader reads local files only — **no network at build or runtime.** To reproduce or
refresh the vendored SVDs from upstream (and verify their pinned SHA-256), see
[`data/svd/SOURCES.md`](data/svd/SOURCES.md) and `scripts/fetch_svds.py`.

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
data/svd/         vendored ground-truth SVDs + SOURCES.md (URLs, licence, sha256)
tests/            pure validator tests + real-SVD loader tests
```

## Scope & limitations (Phase 1)

- **Registers only.** No electrical/timing tables, prose, or errata yet (Tiers 2–3 are later
  phases). There is no MCP server surface yet — that is Phase 2.
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
