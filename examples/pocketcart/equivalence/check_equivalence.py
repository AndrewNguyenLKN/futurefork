#!/usr/bin/env python3
"""Prove the PocketCart candidates share a current contract.

Checks, for the `coupled` and `modular` candidates (directories, or Git refs via --refs):
  1. the test suites are byte-identical (same files, same hashes);
  2. the same set of test IDs exists and every test passes in each candidate;
  3. a scripted request transcript produces byte-identical responses in both
     candidates over in-process WSGI and over a real loopback HTTP server;
  4. the transcript hash equals the recorded golden hash (unless --write-golden).
Also reports which source files are identical vs. different, so reviewers can see
where the two designs actually diverge. Exit code 0 only if every check holds.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CANDIDATES_DIR = HERE.parent / "candidates"
GOLDEN = HERE / "golden-transcript.sha256"
NAMES = ("coupled", "modular")


def tree_hashes(root: Path, sub: str) -> dict[str, str]:
    base = root / sub
    return {
        str(p.relative_to(base)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(base.rglob("*.py"))
        if "__pycache__" not in p.parts
    }


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("PYTHONPATH", None)
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env)


def pytest_summary(root: Path) -> dict:
    base = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider"]
    collected = run(base + ["--collect-only", "-q"], root)
    ids = sorted(l for l in collected.stdout.splitlines() if "::" in l)
    result = run(base + ["-q"], root)
    last = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    return {"returncode": result.returncode, "summary": last, "test_ids": ids}


def transcript(root: Path, transport: str) -> tuple[str, str]:
    result = run([sys.executable, str(HERE / "run_transcript.py"), str(root), transport], HERE)
    if result.returncode != 0:
        raise SystemExit(f"transcript failed ({transport}, {root}):\n{result.stderr}")
    return hashlib.sha256(result.stdout.encode()).hexdigest(), result.stdout


def export_ref(repo: Path, ref: str, dest: Path) -> Path:
    """Materialize a Git ref's tree with `git archive` (never checks anything out in `repo`)."""
    dest.mkdir(parents=True)
    archive = subprocess.run(["git", "-C", str(repo), "archive", ref], capture_output=True, check=True)
    subprocess.run(["tar", "-x", "-C", str(dest)], input=archive.stdout, check=True)
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refs", metavar="REPO", help="check Git refs `coupled` and `modular` in REPO instead of directories")
    ap.add_argument("--candidates-dir", type=Path, default=CANDIDATES_DIR, help="directory holding coupled/ and modular/")
    ap.add_argument("--write-golden", action="store_true", help="record the transcript hash as the golden value")
    ap.add_argument("--report", type=Path, help="write the JSON report here")
    args = ap.parse_args()

    tmp = tempfile.TemporaryDirectory()
    if args.refs:
        roots = {n: export_ref(Path(args.refs), n, Path(tmp.name) / n) for n in NAMES}
        source = {"kind": "git-refs", "repo": str(Path(args.refs).resolve()),
                  "commits": {n: subprocess.run(["git", "-C", args.refs, "rev-parse", n], capture_output=True,
                                                text=True, check=True).stdout.strip() for n in NAMES}}
    else:
        roots = {n: args.candidates_dir / n for n in NAMES}
        source = {"kind": "directories"}

    report: dict = {"source": source, "checks": {}}
    a, b = (roots[n] for n in NAMES)

    tests = {n: tree_hashes(roots[n], "tests") for n in NAMES}
    report["checks"]["tests_byte_identical"] = tests["coupled"] == tests["modular"]
    report["test_file_sha256"] = tests["coupled"]

    src = {n: tree_hashes(roots[n], "src/pocketcart") for n in NAMES}
    report["source_files"] = {
        "identical": sorted(f for f in src["coupled"] if src["modular"].get(f) == src["coupled"][f]),
        "differ": sorted(f for f in src["coupled"] if f in src["modular"] and src["modular"][f] != src["coupled"][f]),
        "only_coupled": sorted(set(src["coupled"]) - set(src["modular"])),
        "only_modular": sorted(set(src["modular"]) - set(src["coupled"])),
    }

    runs = {n: pytest_summary(roots[n]) for n in NAMES}
    report["pytest"] = {n: {k: v for k, v in runs[n].items() if k != "test_ids"} | {"test_count": len(runs[n]["test_ids"])} for n in NAMES}
    report["checks"]["same_test_ids"] = runs["coupled"]["test_ids"] == runs["modular"]["test_ids"] and bool(runs["coupled"]["test_ids"])
    report["checks"]["all_tests_pass"] = all(runs[n]["returncode"] == 0 for n in NAMES)

    hashes = {}
    bodies = {}
    for n in NAMES:
        for transport in ("wsgi", "http"):
            hashes[f"{n}/{transport}"], bodies[f"{n}/{transport}"] = transcript(roots[n], transport)
    report["transcript_sha256"] = hashes
    report["checks"]["transcripts_identical"] = len(set(hashes.values())) == 1
    steps = json.loads(bodies["coupled/wsgi"])
    report["transcript_requests"] = len(steps)
    statuses: dict[str, int] = {}
    for s in steps:
        statuses[str(s["status"])] = statuses.get(str(s["status"]), 0) + 1
    report["transcript_status_counts"] = statuses

    digest = hashes["coupled/wsgi"]
    if args.write_golden:
        GOLDEN.write_text(digest + "\n")
    report["checks"]["matches_golden"] = GOLDEN.exists() and GOLDEN.read_text().strip() == digest
    report["ok"] = all(report["checks"].values())

    text = json.dumps(report, indent=2, sort_keys=True)
    if args.report:
        args.report.write_text(text + "\n")
    print(text)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
