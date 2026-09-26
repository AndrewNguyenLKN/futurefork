"""Evaluator-owned protected test packs: baseline behavior, isolation, hashing, tamper detection."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from futurefork import testpack
from futurefork.scenario import load_scenario

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "scenarios" / "demo"
CANDIDATES = ROOT / "examples" / "pocketcart" / "candidates"
SCENARIO_IDS = ["partial-refund", "organization-pricing", "ordered-discounts"]
CANDIDATE_NAMES = ["coupled", "modular"]
FROZEN = testpack.load_frozen()


def scenario(sid: str):
    return load_scenario(DEMO / f"{sid}.yaml")


def pack_dir(sid: str) -> Path:
    return ROOT / scenario(sid).protected_tests.source


def load_model(sid: str):
    path = pack_dir(sid) / "oracle_model.py"
    spec = importlib.util.spec_from_file_location(f"oracle_{sid.replace('-', '_')}", path)
    module = importlib.util.module_from_spec(spec)
    previous, sys.dont_write_bytecode = sys.dont_write_bytecode, True  # never write into a pack directory
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def prepare_worktree(tmp_path: Path, candidate: str, sid: str) -> tuple[Path, list[str]]:
    """A copy of the candidate with the verified pack mounted read-only where the scenario says."""
    work = tmp_path / f"{candidate}-{sid}"
    shutil.copytree(CANDIDATES / candidate, work, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    sc = scenario(sid)
    testpack.mount_pack(pack_dir(sid), work / sc.protected_tests.mount, FROZEN[sid]["files"])
    cmd = [sys.executable if a == "python" else a for a in sc.protected_test_command]
    return work, cmd


def run_pack(work: Path, cmd: list[str], *extra: str) -> tuple[subprocess.CompletedProcess, ET.Element]:
    junit = work / "junit.xml"
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [*cmd, "-p", "no:cacheprovider", f"--junitxml={junit}", *extra],
        cwd=work, capture_output=True, text=True, env=env,
    )
    return result, ET.parse(junit).getroot()


def outcomes(root: ET.Element) -> dict[str, list]:
    buckets: dict[str, list] = {"passed": [], "failed": [], "error": [], "skipped": []}
    for case in root.iter("testcase"):
        name = f"{case.get('classname')}::{case.get('name')}"
        if case.find("failure") is not None:
            buckets["failed"].append((name, case.find("failure").get("message", "")))
        elif case.find("error") is not None:
            buckets["error"].append((name, case.find("error").get("message", "")))
        elif case.find("skipped") is not None:
            buckets["skipped"].append((name, ""))
        else:
            buckets["passed"].append((name, ""))
    return buckets


# --- structure and freezing ------------------------------------------------------------------

@pytest.mark.parametrize("sid", SCENARIO_IDS)
def test_every_scenario_has_a_frozen_pack_at_its_declared_source(sid):
    source = pack_dir(sid)
    assert source.is_dir() and source.name == sid
    assert sid in FROZEN
    assert testpack.verify(source, FROZEN[sid]["files"]) == FROZEN[sid]["pack_sha256"]
    assert any(name.startswith("test_") for name in FROZEN[sid]["files"])


def test_frozen_manifest_covers_exactly_the_scenarios():
    assert sorted(FROZEN) == sorted(SCENARIO_IDS)
    assert sorted(p.name for p in testpack.PACKS_DIR.iterdir() if p.is_dir()) == sorted(SCENARIO_IDS)


def test_freeze_script_check_passes():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "freeze_protected_packs.py"), "check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_pack_hashes_are_distinct_and_deterministic():
    hashes = [testpack.pack_sha256(pack_dir(s)) for s in SCENARIO_IDS]
    assert len(set(hashes)) == 3
    assert hashes == [testpack.pack_sha256(pack_dir(s)) for s in SCENARIO_IDS]
    assert all(len(h) == 64 for h in hashes)


def test_hash_is_independent_of_location_mtime_and_bytecode(tmp_path):
    copy = tmp_path / "elsewhere" / "pack"
    shutil.copytree(pack_dir("partial-refund"), copy)
    for i, path in enumerate(sorted(copy.iterdir())):
        os.utime(path, (1_000_000 + i, 1_000_000 + i))
    (copy / "__pycache__").mkdir(exist_ok=True)
    (copy / "__pycache__" / "x.cpython-314.pyc").write_bytes(b"junk")
    (copy / ".pytest_cache").mkdir()
    (copy / ".pytest_cache" / "v").write_text("cache")
    assert testpack.pack_sha256(copy) == FROZEN["partial-refund"]["pack_sha256"]


# --- collection and unchanged-candidate behavior ------------------------------------------------

@pytest.mark.parametrize("candidate", CANDIDATE_NAMES)
@pytest.mark.parametrize("sid", SCENARIO_IDS)
def test_pack_collects_cleanly_against_each_candidate(tmp_path, candidate, sid):
    work, cmd = prepare_worktree(tmp_path, candidate, sid)
    result = subprocess.run([*cmd, "-p", "no:cacheprovider", "--collect-only", "-q"], cwd=work,
                            capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    assert result.returncode == 0, result.stdout + result.stderr
    counts = [int(n) for n in re.findall(r"^\S+\.py: (\d+)$", result.stdout, re.M)]
    assert sum(counts) >= 15, result.stdout
    assert scenario(sid).protected_tests.mount in result.stdout


@pytest.mark.parametrize("candidate", CANDIDATE_NAMES)
@pytest.mark.parametrize("sid", SCENARIO_IDS)
def test_unchanged_candidates_pass_guards_and_fail_every_future_test(tmp_path, candidate, sid):
    work, cmd = prepare_worktree(tmp_path, candidate, sid)

    _, guard_xml = run_pack(work, cmd, "-m", "guard")
    guards = outcomes(guard_xml)
    assert guards["passed"], "the pack must contain regression guards"
    assert not (guards["failed"] or guards["error"] or guards["skipped"]), guards

    _, future_xml = run_pack(work, cmd, "-m", "not guard")
    future = outcomes(future_xml)
    assert future["failed"], "the pack must contain future-behavior tests"
    # Nothing may pass by accident, be skipped, or error out in setup/import.
    assert not (future["passed"] or future["error"] or future["skipped"]), future
    # Each failure is a failed assertion about missing behavior, not a crash in the test code.
    not_assertions = [(n, m) for n, m in future["failed"] if not m.startswith(("AssertionError", "assert "))]
    assert not not_assertions, not_assertions


def test_baseline_counts_are_identical_for_both_candidates(tmp_path):
    """Same tests, same outcomes on both candidates: the oracle does not favor either design."""
    seen = {}
    for candidate in CANDIDATE_NAMES:
        for sid in SCENARIO_IDS:
            work, cmd = prepare_worktree(tmp_path, candidate, sid)
            _, xml = run_pack(work, cmd)
            seen[candidate, sid] = {k: sorted(n for n, _ in v) for k, v in outcomes(xml).items()}
    for sid in SCENARIO_IDS:
        assert seen["coupled", sid] == seen["modular", sid]


def test_running_the_pack_does_not_change_its_source_hash(tmp_path):
    work, cmd = prepare_worktree(tmp_path, "coupled", "ordered-discounts")
    run_pack(work, cmd)
    assert testpack.verify(work / scenario("ordered-discounts").protected_tests.mount,
                           FROZEN["ordered-discounts"]["files"])


# --- isolation from candidates ----------------------------------------------------------------------

def test_no_protected_material_lives_in_or_is_named_by_candidates():
    for path in CANDIDATES.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        text = path.read_text()
        for marker in ("futurefork-evaluator", "protected-tests", "oracle_model", "PACKS.json"):
            assert marker not in text, f"{path} mentions {marker}"


def test_packs_are_outside_every_editable_path():
    for sid in SCENARIO_IDS:
        rel = pack_dir(sid).relative_to(ROOT).as_posix()
        assert not rel.startswith("examples/")
        assert not rel.startswith(("src/", "tests/"))


def test_candidate_ref_script_only_snapshots_the_candidate_directory():
    script = (ROOT / "scripts" / "create_candidate_refs.sh").read_text()
    assert 'SRC="$REPO/examples/pocketcart/candidates"' in script
    assert "scenarios" not in script


# --- the oracle model itself (hand-derived expectations, independent of any candidate) ------------------

def test_refund_model_allocation_literals():
    m = load_model("partial-refund")
    assert m.allocate_line_discounts([2000, 1250, 199], 862) == [500, 312, 50]   # two leftover cents
    assert m.allocate_line_discounts([2000, 1250], 325) == [200, 125]
    assert m.allocate_line_discounts([0, 5000], 100) == [0, 100]                 # ineligible line gets nothing
    assert m.allocate_line_discounts([100, 100, 100], 100) == [34, 33, 33]       # ties: earlier line first
    assert m.allocate_line_discounts([100, 100], 0) == [0, 0]
    assert m.allocate_line_discounts([0, 0], 5) == [0, 0]
    assert [m.unit_discount(149, 3, j, 1) for j in range(3)] == [49, 50, 50]
    assert m.unit_discount(149, 3, 0, 2) == 99 and m.unit_discount(149, 3, 2, 1) == 50


def test_refund_model_invariants_hold_for_many_inputs():
    m = load_model("partial-refund")
    for discount in range(0, 400, 7):
        for weights in ([1, 2, 3], [199, 1250, 2000, 0], [5, 5, 5, 5], [4999, 199]):
            shares = m.allocate_line_discounts(weights, discount)
            assert sum(shares) == (discount if sum(weights) else 0)
            assert all(s >= 0 for s in shares)
            assert shares == m.allocate_line_discounts(weights, discount)
    for line_discount in range(0, 90, 11):
        for quantity in (1, 2, 3, 7):
            assert sum(m.unit_discount(line_discount, quantity, j, 1) for j in range(quantity)) == line_discount
            assert m.unit_discount(line_discount, quantity, 0, quantity) == line_discount


def test_refund_model_walks_an_order_to_exactly_the_captured_total():
    m = load_model("partial-refund")
    model = m.RefundModel([("STICKER", 3, 199, True)], 149)
    steps = [model.refund([("STICKER", 1)])["amount_cents"] for _ in range(3)]
    assert steps == [150, 149, 149] and sum(steps) == model.captured == 448


def test_organization_model_literals():
    m = load_model("organization-pricing")
    assert m.organization_discount("org-acme", 4000, 9000) == 800
    assert m.organization_discount("org-globex", 2000, 2000) == 500   # 30% = 600, capped
    assert m.organization_discount("org-acme", 9998, 9998) == 1500    # 20% = 2000, capped
    assert m.organization_discount("org-acme", 199, 199) == 40        # 39.8 rounds half up
    assert m.organization_discount("org-acme", 5000, 3) == 3          # never above the subtotal


def test_composition_model_literals():
    m = load_model("ordered-discounts")
    triple = lambda parts: [(p["source"], p["id"], p["amount_cents"]) for p in parts]
    assert triple(m.compose(4000, 9000, "org-acme", "SAVE10")) == [("organization", "org-acme", 800), ("coupon", "SAVE10", 320)]
    assert triple(m.compose(4000, 9000, "org-globex", "SAVE10")) == [("coupon", "SAVE10", 400), ("organization", "org-globex", 540)]
    assert triple(m.compose(4000, 4000, "org-initech", "SAVE10")) == [("organization", "org-initech", 500), ("coupon", "SAVE10", 0)]
    assert triple(m.compose(1250, 1250, "org-initech", "SAVE25")) == [("organization", "org-initech", 375), ("coupon", "SAVE25", 125)]
    assert triple(m.compose(2000, 2000, "org-acme", "FULLRIDE")) == [("organization", "org-acme", 400), ("coupon", "FULLRIDE", 1600)]
    assert triple(m.compose(2000, 2000, None, "SAVE10")) == [("coupon", "SAVE10", 200)]
    assert m.compose(2000, 2000, None, None) == []
    for org in (None, *m.ORGANIZATIONS):
        for coupon in (None, *m.COUPON_PERCENT):
            total = sum(p["amount_cents"] for p in m.compose(494901, 494901, org, coupon))
            assert total <= (m.ORGANIZATIONS[org][2] if org else 494901)


# --- tamper detection ---------------------------------------------------------------------------------

@pytest.fixture
def pack_copy(tmp_path) -> Path:
    copy = tmp_path / "pack"
    shutil.copytree(pack_dir("partial-refund"), copy)
    return copy


EXPECTED = FROZEN["partial-refund"]["files"]


def test_verify_accepts_an_untouched_copy(pack_copy):
    assert testpack.verify(pack_copy, EXPECTED) == FROZEN["partial-refund"]["pack_sha256"]


def test_modified_file_is_detected(pack_copy):
    target = pack_copy / "test_partial_refund.py"
    target.write_text(target.read_text().replace("== 1800", "== 1801", 1))
    with pytest.raises(testpack.PackMismatch) as info:
        testpack.verify(pack_copy, EXPECTED)
    assert info.value.modified == ["test_partial_refund.py"]
    assert testpack.pack_sha256(pack_copy) != FROZEN["partial-refund"]["pack_sha256"]


def test_single_byte_change_is_detected(pack_copy):
    target = pack_copy / "oracle_model.py"
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(testpack.PackMismatch):
        testpack.verify(pack_copy, EXPECTED)


def test_added_file_is_detected(pack_copy):
    (pack_copy / "test_extra.py").write_text("def test_x():\n    assert True\n")
    with pytest.raises(testpack.PackMismatch) as info:
        testpack.verify(pack_copy, EXPECTED)
    assert info.value.added == ["test_extra.py"]


def test_removed_file_is_detected(pack_copy):
    (pack_copy / "oracle_model.py").unlink()
    with pytest.raises(testpack.PackMismatch) as info:
        testpack.verify(pack_copy, EXPECTED)
    assert info.value.removed == ["oracle_model.py"]


def test_renamed_file_is_detected(pack_copy):
    (pack_copy / "support.py").rename(pack_copy / "helpers.py")
    with pytest.raises(testpack.PackMismatch) as info:
        testpack.verify(pack_copy, EXPECTED)
    assert info.value.added == ["helpers.py"] and info.value.removed == ["support.py"]


def test_deselecting_a_test_by_deleting_it_is_detected(pack_copy):
    target = pack_copy / "test_partial_refund.py"
    kept = [l for l in target.read_text().splitlines(keepends=True) if "test_unknown_order_is_404" not in l]
    target.write_text("".join(kept))
    with pytest.raises(testpack.PackMismatch):
        testpack.verify(pack_copy, EXPECTED)


def test_symlinks_are_rejected(pack_copy):
    (pack_copy / "link.py").symlink_to(pack_copy / "support.py")
    with pytest.raises(ValueError, match="symlinks"):
        testpack.file_hashes(pack_copy)


def test_missing_pack_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        testpack.pack_sha256(tmp_path / "absent")


def test_mount_refuses_a_tampered_source_and_creates_nothing(pack_copy, tmp_path):
    (pack_copy / "test_partial_refund.py").write_text("def test_always_green():\n    pass\n")
    dest = tmp_path / "worktree" / ".futurefork-evaluator" / "partial_refund"
    with pytest.raises(testpack.PackMismatch):
        testpack.mount_pack(pack_copy, dest, EXPECTED)
    assert not dest.exists()


def test_mount_refuses_existing_destination(tmp_path):
    dest = tmp_path / "mount"
    dest.mkdir()
    with pytest.raises(FileExistsError):
        testpack.mount_pack(pack_dir("partial-refund"), dest, EXPECTED)


def test_mounted_pack_is_verified_and_read_only(tmp_path):
    dest = tmp_path / "mount"
    assert testpack.mount_pack(pack_dir("partial-refund"), dest, EXPECTED) == FROZEN["partial-refund"]["pack_sha256"]
    with pytest.raises(PermissionError):
        (dest / "test_partial_refund.py").open("a")


def test_edit_of_mounted_copy_after_mounting_is_detected(tmp_path):
    """What an agent would do if it found the mounted pack: chmod, edit, run. Verification catches it."""
    dest = tmp_path / "mount"
    testpack.mount_pack(pack_dir("partial-refund"), dest, EXPECTED)
    target = dest / "test_partial_refund.py"
    target.chmod(0o644)
    target.write_text("def test_always_green():\n    pass\n")
    with pytest.raises(testpack.PackMismatch) as info:
        testpack.verify(dest, EXPECTED)
    assert info.value.modified == ["test_partial_refund.py"]


def test_edited_frozen_manifest_is_detected(tmp_path):
    """Rewriting PACKS.json to match a tampered pack is caught by comparing with the committed copy."""
    manifest = json.loads(testpack.FROZEN_PACKS.read_text())
    manifest["packs"]["partial-refund"]["files"]["oracle_model.py"] = "0" * 64
    forged = tmp_path / "PACKS.json"
    forged.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    assert forged.read_text() != testpack.FROZEN_PACKS.read_text()
    with pytest.raises(testpack.PackMismatch):
        testpack.verify(pack_dir("partial-refund"), testpack.load_frozen(forged)["partial-refund"]["files"])


def test_build_manifest_reflects_tampering_in_a_scratch_copy(tmp_path):
    scratch = tmp_path / "protected-tests"
    shutil.copytree(testpack.PACKS_DIR, scratch, ignore=shutil.ignore_patterns("PACKS.json"))
    assert testpack.build_manifest(scratch) == json.loads(testpack.FROZEN_PACKS.read_text())
    (scratch / "ordered-discounts" / "oracle_model.py").write_text("# tampered\n")
    tampered = testpack.build_manifest(scratch)
    assert tampered != json.loads(testpack.FROZEN_PACKS.read_text())
    changed = [n for n in SCENARIO_IDS if tampered["packs"][n] != testpack.load_frozen()[n]]
    assert changed == ["ordered-discounts"]


def test_tampered_pack_changes_test_outcomes_but_not_the_frozen_hash(tmp_path):
    """Why hashing matters: an always-green pack passes on the unchanged candidate, and only the hash exposes it."""
    work, cmd = prepare_worktree(tmp_path, "coupled", "partial-refund")
    mount = work / scenario("partial-refund").protected_tests.mount
    forged = mount / "test_partial_refund.py"
    forged.chmod(0o644)
    forged.write_text("def test_forged():\n    assert True\n")
    result, _ = run_pack(work, cmd)
    assert result.returncode == 0                                   # the forged pack would be green...
    with pytest.raises(testpack.PackMismatch):                       # ...but verification refuses it
        testpack.verify(mount, FROZEN["partial-refund"]["files"])
