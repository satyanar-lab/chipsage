# chipsage

Local, zero-cost MCP server giving AI coding tools hallucination-free, citation-backed
access to microcontroller documentation.

---

## Constitution (verbatim — architectural law)

**CONSTITUTION — chipsage**

**MISSION:** Local MCP server (Python, stdio transport) exposing deterministic,
citation-backed MCU documentation tools to Claude Code/Desktop/Cursor. AI reasons;
chipsage verifies. Nothing enters the index without ground truth; nothing leaves without a
source reference.

**TRUST TIERS (architectural law):**

- **Tier 1 REGISTERS:** parsed from vendor CMSIS-SVD via the cmsis-svd PyPI package into
  SQLite. Exact by construction. Loader validates at ingest: no overlapping fields,
  addresses within peripheral ranges, reset values fit field widths. Reject and log
  violations; never silently repair.
- **Tier 2 TABLES (electrical/timing, later phase):** Camelot lattice extraction +
  provenance gate — every numeric cell must appear verbatim in the PyMuPDF text of its
  cited page or the row is rejected. LLMs may repair table STRUCTURE during development but
  may never originate a value.
- **Tier 3 PROSE/ERRATA:** PyMuPDF extraction into SQLite FTS5, page-anchored. Tools return
  excerpts with page numbers; they never paraphrase.

**SCHEMA:** single SQLite file, everything keyed (vendor, chip, peripheral, register,
field). No vendor-specific tables. Vendors are data, not code.

**MCP TOOLS (final set; build order per phases):** lookup_register, decode_dump,
check_write, search_datasheet, get_errata(peripheral-joined), diff_peripherals,
gen_field_access.

**VENDOR ORDER:** RP2040/RP2350 first (SVDs from pico-sdk), STM32 H753+L152 second, ESP32
third (validate community SVD quality at ingest).

**QUALITY GATES (every phase):** pytest suite, ruff clean, GitHub Actions CI green, no
network calls at tool runtime, every tool response carries provenance (SVD version or PDF
page). Eval harness (Phase 5) programmatically cross-checks tier-1 answers against SVD and
reports tier-3 citation accuracy; results table lives in README.

**HONESTY RULES:** README discloses AI-directed development via Claude Code. README states
scope limits plainly (e.g., ESP32 SVD coverage caveats). No feature that requires the model
to assert unverifiable facts.

**PHASES:** (1) repo scaffold, pyproject, SVD→SQLite loader + validation, proven against
rp2040.svd and rp2350.svd downloaded from the pico-sdk GitHub repo, with pytest coverage of
loader and validators. (2) MCP server + lookup_register + decode_dump + check_write.
(3) FTS5 prose indexer + get_errata join. (4) Camelot tier-2 pipeline + provenance gate.
(5) eval harness, CI badge, README with demo GIF, packaged release including pre-built
index.

---

## Operational notes (for future sessions)

These notes do not override the Constitution; they record how we work in this repo.

**Current status:** Phases 1–2 complete (Tier-1 loader + validators; MCP stdio server with
lookup_register / decode_dump / check_write). Phase 3 not started. Do not begin the next
phase without explicit review/approval.

**Environment**
- Python 3.10+; virtualenv lives at `.venv/` (git-ignored).
- Install for development: `.venv/bin/pip install -e ".[dev]"`.

**Layout**
- `src/chipsage/` — package (src layout). Vendor-agnostic; vendors are data, not code.
  - `models.py` — frozen domain dataclasses (Chip/Peripheral/Register/Field), decoupled
    from cmsis-svd so the rest of the code never imports the parser.
  - `svd.py` — the ONLY module that imports `cmsis_svd`; adapts SVD → domain model.
  - `validation.py` — pure Tier-1 validators + `Violation`. No I/O.
  - `schema.py` — SQLite DDL + `SCHEMA_VERSION`.
  - `db.py` — connection helpers: `connect` (read-write, foreign keys on) and `connect_ro`
    (read-only, used by the server).
  - `loader.py` — validates the domain model and inserts valid rows; returns a
    `LoadReport`. Rejects-and-logs; never repairs.
  - `build_index.py` — `chipsage-build` CLI that builds the SQLite index from SVDs.
  - `bits.py` — pure bit math (decode fields, analyse writes). No DB, no MCP; fully tested.
  - `query.py` — citation-backed query layer over the index; returns JSON-ready dicts with
    provenance. The deterministic core the server wraps.
  - `server.py` — `chipsage-mcp` FastMCP stdio server exposing the three Tier-1 tools,
    read-only. Tools annotate `-> dict[str, Any]` so FastMCP emits structuredContent
    (a bare `-> dict` return is rejected for structured output).
- `data/svd/` — vendored ground-truth SVDs + `SOURCES.md` (URLs, licence, sha256).
- `tests/` — `test_validation.py` + `test_bits.py` (pure), `test_loader.py` + `test_query.py`
  (real SVDs / index), and `test_server.py` (MCP tool registration + round-trip).

**Build the index**
- `.venv/bin/chipsage-build --svd data/svd/RP2040.svd data/svd/RP2350.svd -o chipsage.db`
- Built `*.db` files are git-ignored until Phase 5 ships a packaged pre-built index.

**Run the MCP server**
- `.venv/bin/chipsage-mcp --db chipsage.db` — stdio transport, opens the index read-only,
  no network. A client can also point at it via the `CHIPSAGE_DB` env var. See the README
  for an `mcpServers` config snippet.

**Quality gates before any commit** (all must pass):
- `.venv/bin/ruff check .`
- `.venv/bin/pytest`
- No network calls at tool runtime (loading reads local files only).

**Docs are part of every phase — not an afterthought.** Before a phase is presented for
review, its work MUST already be reflected in the user-facing docs:
- the README **phase table** marks the phase ✅ (and the status line is current);
- the README has the sections a user needs for that phase (install/usage/examples), with
  any commands **verified by running them exactly as written** (for MCP install, from a
  directory outside the repo, since clients launch from an arbitrary cwd);
- the CLAUDE.md status line is updated.
A phase whose README still shows it as "planned", or lacks its user-facing section, is not
done — do not present it for review.

**Commits & pushes: ALWAYS delegate to the `git-clerk` subagent.** It is the only actor
that commits/pushes and it writes Conventional Commit messages. Do not run `git commit`
yourself. Never push unless the user explicitly asks.

**Data honesty**
- Tier-1 values come only from vendor SVDs. Never hand-edit or "fix" a value; if a value
  fails validation, it is rejected and logged, not repaired.
- Every stored chip carries provenance (`svd_version`, `svd_source`).
