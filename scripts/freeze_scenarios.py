#!/usr/bin/env python3
"""Write or check scenarios/demo/FROZEN.sha256 (sha256sum format, exact YAML bytes)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from futurefork.scenario import scenario_sha256  # noqa: E402

DEMO = Path(__file__).resolve().parents[1] / "scenarios" / "demo"
FROZEN = DEMO / "FROZEN.sha256"


def current_lines() -> list[str]:
    return [f"{scenario_sha256(p)}  {p.name}" for p in sorted(DEMO.glob("*.yaml"))]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=["write", "check"])
    mode = ap.parse_args().mode
    lines = current_lines()
    if mode == "write":
        FROZEN.write_text("\n".join(lines) + "\n")
        print(f"wrote {FROZEN}")
        return 0
    if FROZEN.read_text().splitlines() != lines:
        print("scenario files differ from FROZEN.sha256", file=sys.stderr)
        return 1
    print("scenarios match FROZEN.sha256")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
