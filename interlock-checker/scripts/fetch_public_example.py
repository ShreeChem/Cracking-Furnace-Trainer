"""Download the public DEXPI reference P&ID (C01) used to show the reader works on real DEXPI.

Source: DEXPI e.V. reference P&ID "C01V04-VER.EX01.xml" (c) DEXPI e.V., as shipped in the
pyDEXPI repository (TU Delft Process Intelligence group). The file is not committed here
because its own redistribution terms are not stated; it is fetched from a pinned commit.

Run from the interlock-checker folder:  python scripts/fetch_public_example.py
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

COMMIT = "83e5a11c4af3635ad12290a4dbe310480eb6d7a3"
URL = (f"https://raw.githubusercontent.com/process-intelligence-research/pyDEXPI/{COMMIT}"
       "/data/C01V04-VER.EX01.xml")
TARGET = Path(__file__).resolve().parent.parent / "examples" / "public" / "C01V04-VER.EX01.xml"


def main() -> int:
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    if TARGET.exists():
        print(f"already present: {TARGET}")
        return 0
    try:
        with urllib.request.urlopen(URL, timeout=60) as resp:
            data = resp.read()
    except Exception as exc:
        print(f"ERROR: could not download {URL}: {exc}", file=sys.stderr)
        return 1
    if b"<PlantModel" not in data[:2000]:
        print("ERROR: the download does not look like a DEXPI Proteus XML file.", file=sys.stderr)
        return 1
    TARGET.write_bytes(data)
    print(f"wrote {TARGET} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
