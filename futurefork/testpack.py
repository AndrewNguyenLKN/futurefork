"""Evaluator-owned protected test packs: deterministic hashing, verification, mounting.

A pack hash covers every file's relative path and bytes, so any edit, addition,
deletion, or rename changes it. Bytecode and pytest caches are ignored because
running the tests legitimately creates them. Symlinks are rejected outright.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKS_DIR = ROOT / "scenarios" / "demo" / "protected-tests"
FROZEN_PACKS = PACKS_DIR / "PACKS.json"
_IGNORED_DIRS = {"__pycache__", ".pytest_cache"}
_IGNORED_SUFFIXES = {".pyc", ".pyo"}


class PackMismatch(Exception):
    """A pack differs from its frozen manifest."""

    def __init__(self, root: Path, modified: list[str], added: list[str], removed: list[str]):
        self.root, self.modified, self.added, self.removed = root, modified, added, removed
        super().__init__(
            f"pack {root} does not match frozen manifest: "
            f"modified={modified} added={added} removed={removed}"
        )


def _walk(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _IGNORED_DIRS)
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if path.suffix in _IGNORED_SUFFIXES:
                continue
            yield path


def file_hashes(root: Path | str) -> dict[str, str]:
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"protected test pack not found: {root}")
    hashes: dict[str, str] = {}
    for path in _walk(root):
        if path.is_symlink():
            raise ValueError(f"symlinks are not allowed in a protected pack: {path}")
        hashes[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def combine(files: dict[str, str]) -> str:
    """The pack hash: sha256 over sorted 'sha256  path' lines."""
    body = "".join(f"{files[p]}  {p}\n" for p in sorted(files))
    return hashlib.sha256(body.encode()).hexdigest()


def pack_sha256(root: Path | str) -> str:
    return combine(file_hashes(root))


def verify(root: Path | str, expected_files: dict[str, str]) -> str:
    """Return the pack hash if `root` matches `expected_files`, else raise PackMismatch."""
    actual = file_hashes(root)
    modified = sorted(p for p in actual if p in expected_files and actual[p] != expected_files[p])
    added = sorted(set(actual) - set(expected_files))
    removed = sorted(set(expected_files) - set(actual))
    if modified or added or removed:
        raise PackMismatch(Path(root), modified, added, removed)
    return combine(actual)


def load_frozen(path: Path = FROZEN_PACKS) -> dict:
    return json.loads(path.read_text())["packs"]


def build_manifest(packs_dir: Path = PACKS_DIR) -> dict:
    packs = {}
    for pack in sorted(p for p in packs_dir.iterdir() if p.is_dir()):
        files = file_hashes(pack)
        packs[pack.name] = {"pack_sha256": combine(files), "files": files}
    return {"schema_version": 1, "packs": packs}


def mount_pack(source: Path | str, dest: Path | str, expected_files: dict[str, str]) -> str:
    """Verify `source`, copy it to `dest`, make files read-only, re-verify the copy.

    Refuses to mount a tampered source or over an existing destination.
    """
    source, dest = Path(source), Path(dest)
    verify(source, expected_files)
    if dest.exists():
        raise FileExistsError(f"mount destination already exists: {dest}")
    shutil.copytree(source, dest, ignore=shutil.ignore_patterns(*_IGNORED_DIRS, "*.pyc"))
    for path in _walk(dest):
        path.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    return verify(dest, expected_files)
