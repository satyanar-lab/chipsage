#!/usr/bin/env python3
"""Re-download the vendored SVD files and verify them against their pinned SHA-256.

This is a *development* helper for reproducing / refreshing `data/svd/`. It is never invoked
at tool runtime — chipsage only ever reads the local, vendored copies. Provenance for the
hashes lives in `data/svd/SOURCES.md`.

Usage:
    python scripts/fetch_svds.py            # download + verify into data/svd/
    python scripts/fetch_svds.py --check    # verify existing files only, no download
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "svd"

# filename -> (url, expected sha-256)
SVDS: dict[str, tuple[str, str]] = {
    "RP2040.svd": (
        "https://raw.githubusercontent.com/raspberrypi/pico-sdk/master/"
        "src/rp2040/hardware_regs/RP2040.svd",
        "1c72330127ae097c8c9a3661b509fcb9a94826d76a5c0d7e259eb605ddd7b0a6",
    ),
    "RP2350.svd": (
        "https://raw.githubusercontent.com/raspberrypi/pico-sdk/master/"
        "src/rp2350/hardware_regs/RP2350.svd",
        "e75578fbc6aee06ddf875fd2fe71d7ab59fc19fb406c7eed58849a6c8cf491fd",
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

    for name, (url, expected) in SVDS.items():
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
