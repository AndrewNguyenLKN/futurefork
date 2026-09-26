#!/usr/bin/env python3
"""Write or check scenarios/demo/protected-tests/PACKS.json (per-file and per-pack sha256)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from futurefork import testpack  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=["write", "check", "show"])
    mode = ap.parse_args().mode
    current = testpack.build_manifest()
    if mode == "show":
        for name, pack in current["packs"].items():
            print(f"{pack['pack_sha256']}  {name}")
        return 0
    text = json.dumps(current, indent=2, sort_keys=True) + "\n"
    if mode == "write":
        testpack.FROZEN_PACKS.write_text(text)
        print(f"wrote {testpack.FROZEN_PACKS}")
        return 0
    if not testpack.FROZEN_PACKS.exists() or testpack.FROZEN_PACKS.read_text() != text:
        print("protected packs differ from PACKS.json", file=sys.stderr)
        return 1
    print("protected packs match PACKS.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
