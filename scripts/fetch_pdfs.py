#!/usr/bin/env python3
"""Re-download the vendored datasheet PDFs and verify them against their pinned SHA-256.

A *development* helper for reproducing / refreshing `data/pdf/`. It is never invoked at tool
runtime — chipsage only ever reads the local, vendored copies. Provenance and licence for the
hashes live in `data/pdf/SOURCES.md`.

Usage:
    python scripts/fetch_pdfs.py            # download + verify into data/pdf/
    python scripts/fetch_pdfs.py --check    # verify existing files only, no download
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "pdf"

# filename -> (url, expected sha-256)
PDFS: dict[str, tuple[str, str]] = {
    "rp2040-datasheet.pdf": (
        "https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf",
        "be56fbb75ba0ae9e26558a73c93ac3e75c2ad4e6878d3b6703de2a76d886ea8c",
    ),
    "rp2350-datasheet.pdf": (
        "https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf",
        "2877d0f270fb6d6a57943bee58aaad536aa027bea1e5b1c4ce2541a3230d4be8",
    ),
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="verify existing files instead of downloading"
    )
    args = parser.parse_args(argv)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    failures = 0

    for name, (url, expected) in PDFS.items():
        dest = DATA_DIR / name
        if args.check:
            if not dest.is_file():
                print(f"MISSING  {name}")
                failures += 1
                continue
            data = dest.read_bytes()
        else:
            print(f"fetching {name} <- {url}")
            with urllib.request.urlopen(url) as resp:  # noqa: S310 (trusted, pinned by hash)
                data = resp.read()

        digest = _sha256(data)
        if digest != expected:
            print(f"MISMATCH {name}: got {digest}, expected {expected}")
            failures += 1
            continue

        if not args.check:
            dest.write_bytes(data)
        print(f"OK       {name} ({len(data):,} bytes)")

    if failures:
        print(f"\n{failures} file(s) failed verification", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
