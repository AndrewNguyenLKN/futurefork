"""P0.2: coupled and modular candidates are behaviorally equivalent today."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
POCKETCART = ROOT / "examples" / "pocketcart"
CHECKER = POCKETCART / "equivalence" / "check_equivalence.py"
REFS_SCRIPT = ROOT / "scripts" / "create_candidate_refs.sh"
GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "FutureFork Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "FutureFork Test", "GIT_COMMITTER_EMAIL": "test@example.invalid",
}


def run_checker(*args: str) -> tuple[int, dict]:
    result = subprocess.run([sys.executable, str(CHECKER), *args], capture_output=True, text=True)
    return result.returncode, json.loads(result.stdout)


@pytest.fixture(scope="module")
def report() -> dict:
    code, data = run_checker()
    assert code == 0, data
    return data


def test_candidates_pass_identical_current_suite(report):
    assert report["checks"]["tests_byte_identical"]
    assert report["checks"]["same_test_ids"]
    assert report["checks"]["all_tests_pass"]
    counts = {n: report["pytest"][n]["test_count"] for n in ("coupled", "modular")}
    assert counts["coupled"] == counts["modular"] >= 40


def test_candidates_expose_identical_observable_behavior(report):
    assert report["checks"]["transcripts_identical"]
    assert len(set(report["transcript_sha256"].values())) == 1
    assert set(report["transcript_sha256"]) == {"coupled/wsgi", "coupled/http", "modular/wsgi", "modular/http"}
    assert report["transcript_requests"] >= 50
    assert {"200", "201", "400", "404", "405", "409", "422"} <= set(report["transcript_status_counts"])


def test_behavior_is_frozen_to_golden_hash(report):
    assert report["checks"]["matches_golden"]


def test_designs_actually_differ_where_intended(report):
    files = report["source_files"]
    assert "discounts.py" in files["only_coupled"]
    assert any(f.startswith("pricing/") for f in files["only_modular"])
    assert {"store.py", "checkout.py", "refunds.py"} <= set(files["differ"])
    assert {"wsgi.py", "catalog.py", "payments.py", "validation.py"} <= set(files["identical"])


def test_no_candidate_mentions_the_future_scenarios():
    banned = ["partial", "organization", "organisation", "compos", "allocat", "policy_id", "tenant"]
    for name in ("coupled", "modular"):
        for path in (POCKETCART / "candidates" / name / "src").rglob("*.py"):
            text = path.read_text().lower()
            for word in banned:
                assert word not in text, f"{path} mentions {word!r}"


# --- sensitivity: the checker must notice real divergence -------------------------

@pytest.fixture
def scratch_candidates(tmp_path) -> Path:
    dest = tmp_path / "candidates"
    shutil.copytree(POCKETCART / "candidates", dest, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    return dest


def test_checker_detects_behavior_divergence(scratch_candidates):
    policy = scratch_candidates / "modular/src/pocketcart/pricing/policy.py"
    policy.write_text(policy.read_text().replace("+ 50) // 100", "+ 0) // 100"))  # floor instead of half-up
    code, data = run_checker("--candidates-dir", str(scratch_candidates))
    assert code == 1
    assert not data["checks"]["transcripts_identical"]
    assert not data["checks"]["all_tests_pass"]


def test_checker_detects_divergent_test_suites(scratch_candidates):
    extra = scratch_candidates / "modular/tests/test_extra.py"
    extra.write_text("def test_extra():\n    assert True\n")
    code, data = run_checker("--candidates-dir", str(scratch_candidates))
    assert code == 1
    assert not data["checks"]["tests_byte_identical"]
    assert not data["checks"]["same_test_ids"]


def test_checker_detects_silent_change_that_tests_do_not_cover(scratch_candidates):
    """The transcript catches drift the test suite misses (extra JSON key on one side)."""
    checkout = scratch_candidates / "coupled/src/pocketcart/checkout.py"
    checkout.write_text(checkout.read_text().replace('"status": order["status"],', '"status": order["status"], "note": "x",', 1))
    code, data = run_checker("--candidates-dir", str(scratch_candidates))
    assert code == 1
    assert not data["checks"]["transcripts_identical"]


# --- Git refs ------------------------------------------------------------------------

@pytest.fixture
def temp_repo(tmp_path) -> Path:
    """A repository with no commits (like the real one) holding a copy of the candidates."""
    repo = tmp_path / "repo"
    shutil.copytree(POCKETCART / "candidates", repo / "examples/pocketcart/candidates",
                    ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True, env=GIT_ENV)
    (repo / "PLANNING.md").write_text("uncommitted user file\n")
    return repo


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, env=GIT_ENV).stdout.strip()


def test_candidate_refs_are_created_without_touching_worktree_or_head(temp_repo):
    subprocess.run([str(REFS_SCRIPT), str(temp_repo)], check=True, capture_output=True, env=GIT_ENV)
    assert set(git(temp_repo, "for-each-ref", "--format=%(refname:short)").split()) == {"coupled", "modular"}
    for ref in ("coupled", "modular"):
        assert git(temp_repo, "rev-list", "--parents", "-n1", ref).count(" ") == 0  # parentless
        assert git(temp_repo, "ls-tree", "--name-only", ref).split() == ["pyproject.toml", "src", "tests"]
    # HEAD is still unborn, nothing was staged, the user's file is untouched and untracked.
    assert subprocess.run(["git", "-C", str(temp_repo), "rev-parse", "--verify", "-q", "HEAD"], env=GIT_ENV).returncode != 0
    assert git(temp_repo, "diff", "--cached", "--name-only") == ""
    assert (temp_repo / "PLANNING.md").read_text() == "uncommitted user file\n"
    assert "PLANNING.md" in git(temp_repo, "status", "--porcelain")


def test_refs_script_refuses_to_overwrite(temp_repo):
    subprocess.run([str(REFS_SCRIPT), str(temp_repo)], check=True, capture_output=True, env=GIT_ENV)
    before = git(temp_repo, "rev-parse", "coupled", "modular")
    again = subprocess.run([str(REFS_SCRIPT), str(temp_repo)], capture_output=True, text=True, env=GIT_ENV)
    assert again.returncode != 0 and "already exists" in again.stderr
    assert git(temp_repo, "rev-parse", "coupled", "modular") == before


def test_equivalence_holds_when_checked_from_git_refs(temp_repo):
    subprocess.run([str(REFS_SCRIPT), str(temp_repo)], check=True, capture_output=True, env=GIT_ENV)
    code, data = run_checker("--refs", str(temp_repo))
    assert code == 0, data
    assert data["source"]["kind"] == "git-refs"
    assert set(data["source"]["commits"]) == {"coupled", "modular"}
    assert data["checks"]["matches_golden"]
    # The refs reproduce exactly the directory results.
    _, from_dirs = run_checker()
    assert data["transcript_sha256"] == from_dirs["transcript_sha256"]
    assert data["test_file_sha256"] == from_dirs["test_file_sha256"]
