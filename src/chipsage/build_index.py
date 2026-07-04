"""``chipsage-build`` — build the chipsage SQLite index from CMSIS-SVD files (and datasheets).

Example::

    chipsage-build --svd data/svd/RP2040.svd data/svd/RP2350.svd \\
                   --pdf data/pdf/rp2040-datasheet.pdf data/pdf/rp2350-datasheet.pdf \\
                   -o chipsage.db

Reads only local files (no network), rebuilds the output database from scratch, and prints a
one-line summary per chip. SVDs supply Tier-1 registers; ``--pdf`` datasheets add Tier-3
prose (FTS5) and errata for a chip already loaded from its SVD. ``--strict`` makes any ingest
violation a non-zero exit so CI can fail on a poisoned SVD.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .loader import build_database


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="chipsage-build",
        description="Build the chipsage Tier-1 SQLite index from CMSIS-SVD files.",
    )
    parser.add_argument(
        "--svd", nargs="+", required=True, type=Path, help="one or more SVD files to ingest"
    )
    parser.add_argument(
        "--pdf",
        nargs="*",
        default=[],
        type=Path,
        help="datasheet PDF(s) to index for Tier-3 prose + errata (chip inferred from filename)",
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("chipsage.db"), help="output SQLite path"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="log every rejected register and field"
    )
    parser.add_argument(
        "--strict", action="store_true", help="exit non-zero if any ingest violation occurs"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    missing = [str(p) for p in list(args.svd) + list(args.pdf) if not p.is_file()]
    if missing:
        print(f"error: input file(s) not found: {', '.join(missing)}", file=sys.stderr)
        return 2

    if args.output.exists():
        args.output.unlink()

    reports = build_database(args.svd, args.output)

    total_violations = 0
    for report in reports:
        total_violations += len(report.violations)
        summary = (
            f"{report.vendor}/{report.chip}: {report.peripherals} peripherals, "
            f"{report.registers_inserted} registers, {report.fields_inserted} fields, "
            f"{report.enums_inserted} enums"
        )
        if report.violations:
            summary += (
                f" — REJECTED {report.registers_rejected} register(s), "
                f"{report.fields_rejected} field(s)"
            )
        print(summary)

    if args.pdf:
        from .docs_index import index_documents

        for doc in index_documents(args.output, args.pdf):
            print(
                f"{doc.chip} datasheet ({doc.source}): {doc.pages_indexed} pages, "
                f"{doc.errata_indexed} errata across {len(doc.errata_blocks)} blocks"
            )

    print(f"wrote {args.output}")

    if args.strict and total_violations:
        print(f"strict: {total_violations} ingest violation(s) detected", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
