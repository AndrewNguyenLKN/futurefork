"""P0.5: isolated Git execution. Every test uses temporary repositories only.

A module-scoped guard proves the real repository, its refs, and the P0.3 worktree are unchanged
by this whole module.
"""

from __future__ import annotations

import _thread
import contextlib
import dataclasses
import hashlib
import os
import re
import shutil
import stat
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from futurefork import worktrees as wtmod
from futurefork.manifest import Outcome, OutcomeClass, outcome_class
from futurefork.worktrees import (
    CandidateContaminatedError,
    CleanupError,
    CollisionError,
    ConfinementError,
    DirtyCandidateError,
    GitCommandError,
    GitTimeoutError,
    InvalidIdError,
    InvalidRefError,
    NotACommitError,
    PathCollisionError,
    RegisteredCollisionError,
    RunIdInUseError,
    SourceChangedError,
    VerificationError,
    WorktreeAddError,
    WorktreeError,
    WorktreeManager,
)

ROOT = Path(__file__).resolve().parents[1]
P03 = Path("/private/tmp/futurefork-p03-modular")
REAL_GIT = shutil.which("git")
GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "FutureFork Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "FutureFork Test", "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
}


# --- a guard: the real repo, its refs, and the P0.3 worktree must be untouched by this module ---------------

def _content_hash(root: Path) -> str:
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    files = subprocess.run(["git", "-C", str(root), "ls-files", "-co", "--exclude-standard", "-z"],
                           capture_output=True, env=env).stdout.split(b"\0")
    digest = hashlib.sha256()
    for name in sorted(f for f in files if f):
        path = root / name.decode()
        if path.is_file():
            digest.update(name + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _real_state() -> dict:
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    git = lambda *a: subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True, env=env).stdout
    state = {
        "refs": git("for-each-ref", "--format=%(refname) %(objectname)"),
        "head": git("rev-parse", "HEAD"),
        "worktrees": git("worktree", "list", "--porcelain"),
        "status": git("status", "--porcelain", "--untracked-files=all"),
        "content": _content_hash(ROOT),
    }
    if P03.exists():
        state["p03_content"] = _content_hash(P03)
        state["p03_status"] = subprocess.run(["git", "-C", str(P03), "status", "--porcelain=v1", "--untracked-files=all"],
                                             capture_output=True, text=True, env=env).stdout
        state["p03_head"] = subprocess.run(["git", "-C", str(P03), "rev-parse", "HEAD"], capture_output=True, text=True, env=env).stdout
    return state


@pytest.fixture(scope="module", autouse=True)
def real_repository_is_untouched():
    before = _real_state()
    assert "coupled" in before["refs"] and "modular" in before["refs"]
    yield
    after = _real_state()
    assert after == before, {k: (before[k], after[k]) for k in before if before[k] != after[k]}


# --- temporary repositories ----------------------------------------------------------------------------------------

def git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, env=GIT_ENV)
    if check and result.returncode:
        raise AssertionError(f"git {args} failed: {result.stderr}")
    return result.stdout.strip()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def make_candidate(repo: Path, name: str, marker: str, extra: dict[str, str] | None = None) -> None:
    git(repo, "checkout", "-q", "--orphan", name)
    git(repo, "rm", "-rfq", "--ignore-unmatch", ".")
    write(repo / "pyproject.toml", f"[project]\nname = 'pocketcart-{name}'\n")
    write(repo / "src" / "pocketcart" / "__init__.py", f"CANDIDATE = '{marker}'\n")
    write(repo / "tests" / "test_x.py", "def test_x():\n    assert True\n")
    for rel, text in (extra or {}).items():
        write(repo / rel, text)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", f"candidate {name}")


@pytest.fixture
def repo(tmp_path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    write(path / "ORCHESTRATOR.md", "orchestrator file\n")
    write(path / "scenarios" / "demo" / "protected-tests" / "pack" / "test_secret.py", "SECRET = 1\n")
    git(path, "add", "-A")
    git(path, "commit", "-qm", "orchestrator")
    make_candidate(path, "coupled", "coupled")
    make_candidate(path, "modular", "modular")
    git(path, "checkout", "-q", "main")
    assert path != ROOT and ROOT not in path.parents
    return path


@pytest.fixture
def root(tmp_path) -> Path:
    return tmp_path / "worktrees"


@pytest.fixture
def mgr(repo, root) -> WorktreeManager:
    return WorktreeManager(repo, root)


def rid(i: int = 0, candidate: str = "modular") -> str:
    return f"20260927T0030{i:02d}Z-{candidate}-partial-refund"


def reservations(manager: WorktreeManager) -> list[str]:
    return sorted(p.name for p in (manager.root / ".reservations").iterdir())


def registered_paths(manager: WorktreeManager) -> set[str]:
    return {e["realpath"] for e in manager.registered()}


def ref_snapshot(repo: Path) -> dict:
    return {
        "refs": git(repo, "for-each-ref", "--format=%(refname) %(objectname)"),
        "head": git(repo, "rev-parse", "HEAD"),
        "modular_tree": git(repo, "rev-parse", "modular^{tree}"),
        "coupled_tree": git(repo, "rev-parse", "coupled^{tree}"),
    }


def make_fake_git(tmp_path: Path, script_body: str, name: str = "fake-git") -> str:
    """A bash wrapper around real git; `script_body` may intercept subcommands before delegating."""
    path = tmp_path / name
    path.write_text(f'#!/usr/bin/env bash\nREAL="{REAL_GIT}"\n# argv: git -c a -c b <sub> <subsub> ...\nSUB="$5"; SUB2="$6"\n'
                    + textwrap.dedent(script_body) + '\nexec "$REAL" "$@"\n')
    path.chmod(0o755)
    return str(path)


@contextlib.contextmanager
def forbid_recursive_deletes():
    """Fail if Python tries to delete a directory tree or anything other than a reservation file."""
    def boom(*a, **k):
        raise AssertionError(f"forbidden deletion attempted: {a}")

    real_unlink, real_remove = os.unlink, os.remove
    unlinked: list[str] = []

    def guarded_unlink(path, *a, **k):
        assert f"{os.sep}.reservations{os.sep}" in str(path), f"unlink outside reservations: {path}"
        unlinked.append(str(path))
        return real_unlink(path, *a, **k)

    patches = [(shutil, "rmtree", boom), (os, "rmdir", boom), (os, "removedirs", boom),
               (os, "unlink", guarded_unlink), (os, "remove", guarded_unlink)]
    saved = [(o, n, getattr(o, n)) for o, n, _ in patches]
    try:
        for o, n, f in patches:
            setattr(o, n, f)
        yield unlinked
    finally:
        for o, n, f in saved:
            setattr(o, n, f)
    assert real_unlink and real_remove


# --- 1. creation: resolved OID, detached, exact tree --------------------------------------------------------------------

def test_worktree_is_detached_at_the_resolved_commit_with_the_candidate_tree(mgr, repo):
    commit = git(repo, "rev-parse", "modular")
    wt = mgr.create(rid(), "modular")
    assert wt.commit == commit and wt.tree == git(repo, "rev-parse", "modular^{tree}")
    assert wt.path == mgr.root / rid() and wt.full_ref == "refs/heads/modular"
    assert git(wt.path, "rev-parse", "HEAD") == commit
    assert subprocess.run(["git", "-C", str(wt.path), "symbolic-ref", "-q", "HEAD"], capture_output=True).returncode == 1
    assert git(wt.path, "rev-parse", "HEAD^{tree}") == wt.tree
    tracked = set(git(wt.path, "ls-files").split("\n"))
    assert tracked == set(git(repo, "ls-tree", "-r", "--name-only", commit).split("\n"))
    assert set(os.listdir(wt.path)) == {".git", "pyproject.toml", "src", "tests"}
    assert (wt.path / "src/pocketcart/__init__.py").read_text() == "CANDIDATE = 'modular'\n"
    assert not (wt.path / "ORCHESTRATOR.md").exists() and not (wt.path / "scenarios").exists()
    mgr.remove(wt)


def test_two_candidates_get_their_own_snapshots(mgr):
    a, b = mgr.create(rid(1, "coupled"), "coupled"), mgr.create(rid(2), "modular")
    assert (a.path / "src/pocketcart/__init__.py").read_text() != (b.path / "src/pocketcart/__init__.py").read_text()
    assert a.path != b.path
    mgr.remove(a), mgr.remove(b)


def test_candidate_ref_forms_and_annotated_tags(mgr, repo):
    git(repo, "tag", "-a", "-m", "release", "v1", "modular")
    for i, ref in enumerate(["modular", "refs/heads/modular", "v1", "refs/tags/v1"]):
        wt = mgr.create(rid(i), ref)
        assert wt.commit == git(repo, "rev-parse", "modular")
        mgr.remove(wt)
    git(repo, "tag", "modular", "coupled")                      # a tag with the same short name: branches win
    wt = mgr.create(rid(9), "modular")
    assert wt.full_ref == "refs/heads/modular" and wt.commit == git(repo, "rev-parse", "refs/heads/modular")
    mgr.remove(wt)


def test_ref_is_resolved_once_and_the_worktree_is_built_from_the_oid(repo, root, tmp_path):
    """Count ref-resolving git calls: create() must not re-resolve the branch name for the add."""
    log = tmp_path / "calls.log"
    fake = make_fake_git(tmp_path, f'echo "$SUB $SUB2 ${{@: -1}}" >> "{log}"')
    m = WorktreeManager(repo, root, git_executable=fake)
    log.write_text("")
    wt = m.create(rid(), "modular")
    add = [l for l in log.read_text().splitlines() if l.startswith("worktree add")]
    assert len(add) == 1 and add[0].endswith(wt.commit), add       # the add received the OID, not the ref name
    m.remove(wt)


# --- 2. source refs never change -----------------------------------------------------------------------------------------------------

def test_source_refs_oids_and_trees_are_unchanged_by_create_edit_and_cleanup(mgr, repo):
    before = ref_snapshot(repo)
    with mgr.worktree(rid(), "modular", watch_refs=["coupled", "main"]) as wt:
        write(wt.path / "src/pocketcart/new_file.py", "x = 1\n")
        (wt.path / "src/pocketcart/__init__.py").write_text("CANDIDATE = 'edited'\n")
        git(wt.path, "add", "-A")
        git(wt.path, "commit", "-qm", "agent commit inside the detached worktree")
        assert ref_snapshot(repo) == before                  # even after a commit, no ref moved
    assert ref_snapshot(repo) == before
    assert registered_paths(mgr) == {os.path.realpath(repo)}


def test_candidate_branch_is_never_checked_out(mgr, repo):
    wt = mgr.create(rid(), "modular")
    assert all(e.get("branch") != "refs/heads/modular" for e in mgr.registered())
    mgr.remove(wt)


def test_moving_a_source_ref_during_the_run_is_reported_after_cleanup(mgr, repo):
    with pytest.raises(SourceChangedError) as info:
        with mgr.worktree(rid(), "modular", watch_refs=["coupled"]):
            git(repo, "branch", "-f", "coupled", "modular")
    assert "coupled" in info.value.details["moved"]
    assert not (mgr.root / rid()).exists()                    # cleanup still ran
    git(repo, "branch", "-f", "coupled", "coupled@{1}", check=False)


def test_dirty_root_orchestrator_does_not_block_creation_from_a_clean_commit(mgr, repo):
    (repo / "ORCHESTRATOR.md").write_text("locally modified\n")
    write(repo / "UNTRACKED.txt", "untracked\n")
    before = git(repo, "status", "--porcelain", "--untracked-files=all")
    assert before
    wt = mgr.create(rid(), "modular")
    assert git(wt.path, "status", "--porcelain", "--untracked-files=all") == ""
    assert wt.source_dirty is False
    mgr.remove(wt)
    assert git(repo, "status", "--porcelain", "--untracked-files=all") == before
    assert (repo / "ORCHESTRATOR.md").read_text() == "locally modified\n"


def test_edits_stay_inside_their_own_worktree(mgr, repo):
    a, b = mgr.create(rid(1), "modular"), mgr.create(rid(2), "modular")
    write(a.path / "src/pocketcart/only_in_a.py", "a = 1\n")
    (a.path / "pyproject.toml").write_text("changed\n")
    assert git(b.path, "status", "--porcelain") == ""
    assert not (b.path / "src/pocketcart/only_in_a.py").exists()
    assert "changed" not in (repo / "ORCHESTRATOR.md").read_text()
    assert not list(repo.rglob("only_in_a.py"))
    mgr.remove(a), mgr.remove(b)


# --- dirty candidate checkouts ------------------------------------------------------------------------------------------------------------

def test_dirty_checkout_of_the_candidate_branch_is_detected(mgr, repo, tmp_path):
    checkout = tmp_path / "candidate-checkout"
    git(repo, "worktree", "add", "-q", str(checkout), "modular")
    (checkout / "pyproject.toml").write_text("dirty\n")
    with pytest.raises(DirtyCandidateError) as info:
        mgr.create(rid(), "modular")
    assert info.value.manifest_outcome == "candidate_invalid"
    assert str(checkout) in "".join(info.value.details["worktrees"])
    assert reservations(mgr) == [] and not (mgr.root / rid()).exists()


def test_dirty_candidate_can_be_recorded_instead_of_refused(repo, root, tmp_path):
    m = WorktreeManager(repo, root, dirty_source="record")
    checkout = tmp_path / "candidate-checkout"
    git(repo, "worktree", "add", "-q", str(checkout), "modular")
    write(checkout / "untracked.txt", "u\n")
    wt = m.create(rid(), "modular")
    assert wt.source_dirty is True and wt.dirty_source_paths == (os.path.realpath(checkout),)
    assert git(wt.path, "status", "--porcelain") == ""       # the new worktree is still built from the commit
    assert (checkout / "untracked.txt").exists()              # and the source checkout is left alone
    m.remove(wt)


def test_clean_candidate_checkout_and_dirty_unrelated_checkouts_are_fine(mgr, repo, tmp_path):
    checkout = tmp_path / "candidate-checkout"
    git(repo, "worktree", "add", "-q", str(checkout), "modular")
    other = tmp_path / "other"
    git(repo, "worktree", "add", "-q", "--detach", str(other), "coupled")
    write(other / "dirty.txt", "d\n")                        # dirty, but not the candidate under test
    wt = mgr.create(rid(), "modular")
    assert wt.source_dirty is False
    mgr.remove(wt)


# --- refs: invalid, unresolvable, non-commit --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("ref", ["nope", "refs/heads/nope", "refs/tags/nope", "-x", "a..b", "a b", "", "x.lock", "modular\n",
                                 "f" * 40, "f" * 64, "HEAD~1;rm", "a/", "/a"])
def test_invalid_or_unresolvable_refs_are_rejected_before_any_worktree_exists(mgr, ref):
    with pytest.raises(InvalidRefError) as info:
        mgr.create(rid(), ref)
    assert info.value.manifest_outcome == "candidate_invalid" and info.value.classification == "invalid_ref"
    assert reservations(mgr) == [] and [p.name for p in mgr.root.iterdir()] == [".reservations"]


def test_a_commit_id_is_not_a_ref(mgr, repo):
    with pytest.raises(InvalidRefError):
        mgr.create(rid(), git(repo, "rev-parse", "modular"))


def test_refs_that_do_not_point_to_a_commit_are_rejected(mgr, repo):
    git(repo, "tag", "treetag", git(repo, "rev-parse", "modular^{tree}"))
    git(repo, "tag", "blobtag", git(repo, "rev-parse", "modular:pyproject.toml"))
    for ref in ("treetag", "blobtag", "refs/tags/treetag"):
        with pytest.raises(NotACommitError) as info:
            mgr.create(rid(), ref)
        assert info.value.manifest_outcome == "candidate_invalid"
    assert reservations(mgr) == []


def test_a_candidate_containing_oracle_paths_is_rejected_before_creation(mgr, repo):
    make_candidate(repo, "tainted", "tainted", {"scenarios/demo/protected-tests/x/test_y.py": "leak = 1\n"})
    git(repo, "checkout", "-q", "main")
    with pytest.raises(CandidateContaminatedError) as info:
        mgr.create(rid(), "tainted")
    assert info.value.manifest_outcome == "candidate_invalid"
    assert reservations(mgr) == [] and [p.name for p in mgr.root.iterdir()] == [".reservations"]


# --- 3. ids, confinement -----------------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    "../x", "/abs/path", "a\nb", "a\x00b", "a\x1bb", "x/y", "", "..", ".", "20260927T003000Z-modular-partial-refund/../../x",
    "20260927T003000Z-modular-partial-refund\n", "20260927T003000Z-modular-partial-refund ", "..\\x", "C:\\x", "~/x",
    "20260927T003000Z-Modular-partial-refund", "x" * 300, "20260927T003000-modular-partial-refund", None, 7, b"bytes",
])
def test_bad_run_ids_are_rejected_and_nothing_is_created(mgr, bad):
    with pytest.raises(InvalidIdError):
        mgr.create(bad, "modular")
    with pytest.raises(InvalidIdError):
        mgr.path_for(bad)
    assert [p.name for p in mgr.root.iterdir()] == [".reservations"] and reservations(mgr) == []


def test_valid_ids_map_to_direct_children_of_the_root(mgr):
    path = mgr.path_for(rid(5, "coupled"))
    assert path.parent == mgr.root and path.name == rid(5, "coupled")
    assert os.path.realpath(path) == str(path)


def test_a_preexisting_symlink_at_the_run_path_is_a_collision_and_the_target_is_untouched(mgr, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    write(outside / "precious.txt", "keep\n")
    os.symlink(outside, mgr.root / rid())
    with pytest.raises(PathCollisionError):
        mgr.create(rid(), "modular")
    assert (outside / "precious.txt").read_text() == "keep\n" and sorted(os.listdir(outside)) == ["precious.txt"]
    assert os.path.islink(mgr.root / rid()) and reservations(mgr) == []


def test_a_dangling_symlink_is_also_a_collision(mgr, tmp_path):
    os.symlink(tmp_path / "does-not-exist", mgr.root / rid())
    with pytest.raises(PathCollisionError):
        mgr.create(rid(), "modular")


def test_root_configuration_is_validated(repo, tmp_path):
    with pytest.raises(ConfinementError):
        WorktreeManager(repo, "relative/root")
    with pytest.raises(ConfinementError):
        WorktreeManager(repo, repo / "inside")                             # inside the repository
    with pytest.raises(ConfinementError):
        WorktreeManager(repo, repo)
    with pytest.raises(ConfinementError):
        WorktreeManager(repo, tmp_path)                                    # contains the repository
    with pytest.raises(ConfinementError):
        WorktreeManager(repo, tmp_path / "with\nnewline")
    with pytest.raises(ConfinementError):
        WorktreeManager(repo, "/")
    with pytest.raises(ConfinementError):
        WorktreeManager(repo, repo / ".git" / "wt")
    assert not (repo / "inside").exists()


def test_a_root_that_is_a_symlink_into_the_repository_is_rejected(repo, tmp_path):
    (repo / "inside").mkdir()
    link = tmp_path / "rootlink"
    os.symlink(repo / "inside", link)
    with pytest.raises(ConfinementError):
        WorktreeManager(repo, link)
    with pytest.raises(ConfinementError):
        WorktreeManager(repo, link / "deeper")


def test_root_may_not_overlap_forbidden_oracle_locations(repo, tmp_path):
    protected = tmp_path / "protected-tests"
    protected.mkdir()
    for candidate in (protected, protected / "wt", tmp_path):
        with pytest.raises(ConfinementError):
            WorktreeManager(repo, candidate, forbidden_roots=[protected])
    assert WorktreeManager(repo, tmp_path / "fine", forbidden_roots=[protected]).root == tmp_path / "fine"


def test_root_must_be_private(repo, tmp_path):
    loose = tmp_path / "loose"
    loose.mkdir()
    loose.chmod(0o777)
    with pytest.raises(ConfinementError, match="writable"):
        WorktreeManager(repo, loose)
    file_root = tmp_path / "afile"
    file_root.write_text("x")
    with pytest.raises(ConfinementError):
        WorktreeManager(repo, file_root)


def test_reservations_directory_symlink_is_rejected(repo, tmp_path):
    root = tmp_path / "wt"
    root.mkdir(mode=0o700)
    os.symlink(tmp_path, root / ".reservations")
    with pytest.raises(ConfinementError):
        WorktreeManager(repo, root)


def test_default_root_is_under_the_os_temp_directory_and_outside_the_repo():
    import tempfile
    default = wtmod.default_worktree_root()
    assert Path(tempfile.gettempdir()) in default.parents and str(os.getuid()) in default.name
    assert ROOT not in default.parents and default != ROOT


# --- 4. collisions -------------------------------------------------------------------------------------------------------------------------------------

def test_existing_directory_at_the_run_path_is_a_collision_and_is_left_intact(mgr):
    target = mgr.root / rid()
    write(target / "sentinel.txt", "mine\n")
    with pytest.raises(PathCollisionError) as info:
        mgr.create(rid(), "modular")
    assert isinstance(info.value, CollisionError) and info.value.manifest_outcome == "runner_error"
    assert (target / "sentinel.txt").read_text() == "mine\n" and reservations(mgr) == []


def test_a_registered_worktree_at_the_run_path_is_a_collision(mgr, repo):
    target = mgr.root / rid()
    git(repo, "worktree", "add", "-q", "--detach", str(target), "modular")     # registered by someone else
    shutil.move(str(target), str(target) + ".moved")                            # directory gone, registration remains
    assert not target.exists() and os.path.realpath(target) in registered_paths(mgr)
    with pytest.raises(RegisteredCollisionError):
        mgr.create(rid(), "modular")
    assert reservations(mgr) == []


def test_a_registered_worktree_with_a_live_directory_is_a_collision(mgr, repo):
    git(repo, "worktree", "add", "-q", "--detach", str(mgr.root / rid()), "modular")
    with pytest.raises(CollisionError):
        mgr.create(rid(), "modular")
    assert (mgr.root / rid() / "pyproject.toml").exists()


def test_reusing_a_live_run_id_is_refused_by_the_reservation(mgr):
    wt = mgr.create(rid(), "modular")
    with pytest.raises(RunIdInUseError) as info:
        mgr.create(rid(), "modular")
    assert info.value.classification == "collision_run_id_in_use"
    assert wt.path.exists() and reservations(mgr) == [f"{rid()}.json"]
    mgr.remove(wt)
    assert reservations(mgr) == []
    mgr.remove(mgr.create(rid(), "modular"))                                     # the id is reusable after cleanup


def test_concurrent_creation_of_one_run_id_has_exactly_one_winner_threads(mgr):
    results, barrier = [], threading.Barrier(8)

    def attempt():
        barrier.wait()
        try:
            results.append(("ok", mgr.create(rid(), "modular")))
        except CollisionError as exc:
            results.append(("collision", type(exc).__name__))
        except Exception as exc:  # pragma: no cover - would fail the assertion below
            results.append(("other", repr(exc)))

    threads = [threading.Thread(target=attempt) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    kinds = sorted(k for k, _ in results)
    assert kinds == ["collision"] * 7 + ["ok"], results
    assert {v for k, v in results if k == "collision"} <= {"RunIdInUseError", "PathCollisionError", "RegisteredCollisionError"}
    assert len(registered_paths(mgr)) == 2 and reservations(mgr) == [f"{rid()}.json"]
    mgr.remove(next(v for k, v in results if k == "ok"))


def test_concurrent_creation_of_one_run_id_has_exactly_one_winner_processes(repo, root, tmp_path):
    go = tmp_path / "go"
    script = textwrap.dedent(f"""
        import os, sys, time
        sys.path.insert(0, {str(ROOT)!r})
        from futurefork.worktrees import WorktreeManager, CollisionError
        m = WorktreeManager({str(repo)!r}, {str(root)!r})
        while not os.path.exists({str(go)!r}):
            time.sleep(0.001)
        try:
            m.create({rid()!r}, "modular"); print("OK")
        except CollisionError as e:
            print("COLLISION", type(e).__name__)
        except Exception as e:
            print("OTHER", repr(e))
    """)
    env = {**GIT_ENV, "PYTHONDONTWRITEBYTECODE": "1"}
    procs = [subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
             for _ in range(6)]
    time.sleep(1.0)
    go.write_text("")
    outputs = [p.communicate(timeout=60) for p in procs]
    lines = [o.strip() for o, _ in outputs]
    assert sorted(l.split()[0] for l in lines) == ["COLLISION"] * 5 + ["OK"], (lines, [e for _, e in outputs])
    assert (root / rid() / "pyproject.toml").exists()
    m = WorktreeManager(repo, root)
    assert len(registered_paths(m)) == 2 and reservations(m) == [f"{rid()}.json"]


# --- 5. subprocess safety: argv, timeouts, process groups, bounded output ------------------------------------------------------------------------

def test_git_is_invoked_with_argv_arrays_and_no_shell(mgr, monkeypatch):
    seen = []
    real_popen = subprocess.Popen

    def spy(argv, *a, **k):
        seen.append((argv, k.get("shell"), k.get("start_new_session"), k.get("stdin")))
        return real_popen(argv, *a, **k)

    monkeypatch.setattr(subprocess, "Popen", spy)
    mgr.remove(mgr.create(rid(), "modular"))
    assert seen and all(isinstance(argv, list) and shell is False and new_session is True and stdin == subprocess.DEVNULL
                        for argv, shell, new_session, stdin in seen)
    assert all(argv[0] == "git" and argv[1:3] == ["-c", f"core.hooksPath={os.devnull}"] for argv, *_ in seen)


def test_a_git_timeout_kills_the_whole_process_group_and_leaves_nothing_behind(repo, root, tmp_path):
    pidfile = tmp_path / "child.pid"
    fake = make_fake_git(tmp_path, f'''
        if [ "$SUB" = worktree ] && [ "$SUB2" = add ]; then
            trap "" TERM                       # even a TERM-ignoring child must die
            sleep 300 &
            echo $! > "{pidfile}"
            wait
        fi''')
    m = WorktreeManager(repo, root, git_executable=fake, add_timeout=0.7)
    started = time.monotonic()
    with pytest.raises(GitTimeoutError) as info:
        m.create(rid(), "modular")
    assert time.monotonic() - started < 15 and info.value.classification == "git_timeout"
    assert info.value.manifest_outcome == "runner_error"
    child = int(pidfile.read_text())
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    with pytest.raises(ProcessLookupError):
        os.kill(child, 0)
    assert reservations(m) == [] and not (root / rid()).exists() and len(registered_paths(m)) == 1


def test_keyboard_interrupt_during_git_kills_the_process_group(repo, root, tmp_path):
    pidfile = tmp_path / "child.pid"
    fake = make_fake_git(tmp_path, f'''
        if [ "$SUB" = worktree ] && [ "$SUB2" = add ]; then
            sleep 300 &
            echo $! > "{pidfile}"
            wait
        fi''')
    m = WorktreeManager(repo, root, git_executable=fake, add_timeout=60)
    threading.Timer(0.6, _thread.interrupt_main).start()
    with pytest.raises(KeyboardInterrupt):
        m.create(rid(), "modular")
    child = int(pidfile.read_text())
    time.sleep(0.5)
    with pytest.raises(ProcessLookupError):
        os.kill(child, 0)
    assert reservations(m) == [] and len(registered_paths(m)) == 1


def test_captured_output_is_bounded_but_fully_drained(repo, root, tmp_path):
    fake = make_fake_git(tmp_path, '''
        if [ "$SUB" = status ]; then
            head -c 3000000 /dev/zero | tr '\\0' 'x'
            head -c 2000000 /dev/zero | tr '\\0' 'e' 1>&2
            exit 0
        fi''')
    m = WorktreeManager(repo, root, git_executable=fake, max_output_bytes=1000, git_timeout=20)
    result = m._git(["status"], cwd=repo)
    assert len(result.stdout) == 1000 and len(result.stderr) == 1000 and result.truncated
    assert result.returncode == 0


def test_constructor_validates_limits_and_missing_git_or_repo(repo, root, tmp_path):
    for kw in ({"git_timeout": 0}, {"add_timeout": -1}, {"max_output_bytes": 0}, {"dirty_source": "ignore"}):
        with pytest.raises(ValueError):
            WorktreeManager(repo, root, **kw)
    with pytest.raises(GitCommandError):
        WorktreeManager(repo, root, git_executable=str(tmp_path / "no-such-git"))
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(GitCommandError):
        WorktreeManager(plain, tmp_path / "wt2")
    with pytest.raises(ConfinementError):
        WorktreeManager(tmp_path / "missing", tmp_path / "wt3")


def test_ambient_git_environment_cannot_redirect_the_manager(mgr, repo, monkeypatch, tmp_path):
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "bogus"))
    monkeypatch.setenv("GIT_WORK_TREE", str(tmp_path))
    monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "index"))
    wt = mgr.create(rid(), "modular")
    assert git(wt.path, "rev-parse", "HEAD") == git(repo, "rev-parse", "modular")
    mgr.remove(wt)


def test_repository_hooks_do_not_run(mgr, repo, tmp_path):
    marker = tmp_path / "hook-ran"
    hook = repo / ".git" / "hooks" / "post-checkout"
    hook.write_text(f"#!/bin/sh\ntouch {marker}\n")
    hook.chmod(0o755)
    mgr.remove(mgr.create(rid(), "modular"))
    assert not marker.exists()


# --- typed git failures ---------------------------------------------------------------------------------------------------------------------------------

def test_git_worktree_add_failure_is_typed_and_leaves_no_reservation(repo, root, tmp_path):
    fake = make_fake_git(tmp_path, '''
        if [ "$SUB" = worktree ] && [ "$SUB2" = add ]; then echo "fatal: simulated failure" >&2; exit 128; fi''')
    m = WorktreeManager(repo, root, git_executable=fake)
    with pytest.raises(WorktreeAddError) as info:
        m.create(rid(), "modular")
    assert info.value.details["returncode"] == 128 and "simulated failure" in info.value.details["stderr"]
    assert info.value.classification == "git_worktree_add_failed" and isinstance(info.value, GitCommandError)
    assert reservations(m) == [] and not (root / rid()).exists() and len(registered_paths(m)) == 1


def test_a_failed_add_that_leaves_a_registered_worktree_is_removed_by_git_only(repo, root, tmp_path):
    fake = make_fake_git(tmp_path, '''
        if [ "$SUB" = worktree ] && [ "$SUB2" = add ]; then
            "$REAL" "$@"; echo "fatal: post-add failure" >&2; exit 1
        fi''')
    m = WorktreeManager(repo, root, git_executable=fake)
    with forbid_recursive_deletes():
        with pytest.raises(WorktreeAddError):
            m.create(rid(), "modular")
    assert not (root / rid()).exists() and reservations(m) == [] and len(registered_paths(m)) == 1


def test_a_failed_add_that_leaves_an_unregistered_directory_is_preserved_with_its_reservation(repo, root, tmp_path):
    fake = make_fake_git(tmp_path, f'''
        if [ "$SUB" = worktree ] && [ "$SUB2" = add ]; then
            mkdir -p "{root / rid()}"; echo partial > "{root / rid()}/partial.txt"
            echo "fatal: died midway" >&2; exit 128
        fi''')
    m = WorktreeManager(repo, root, git_executable=fake)
    with forbid_recursive_deletes():
        with pytest.raises(WorktreeAddError):
            m.create(rid(), "modular")
    assert (root / rid() / "partial.txt").read_text() == "partial\n"     # never deleted manually
    assert reservations(m) == [f"{rid()}.json"]                            # and the id stays blocked
    with pytest.raises(RunIdInUseError):
        m.create(rid(), "modular")


def test_verification_failure_removes_the_worktree_and_reports_it(repo, root, tmp_path):
    fake = make_fake_git(tmp_path, '''
        if [ "$SUB" = worktree ] && [ "$SUB2" = add ]; then
            "$REAL" "$@"; rc=$?
            echo junk > "${@: -2:1}/injected.txt"
            exit $rc
        fi''')
    m = WorktreeManager(repo, root, git_executable=fake)
    with pytest.raises(VerificationError, match="not clean"):
        m.create(rid(), "modular")
    assert not (root / rid()).exists() and reservations(m) == [] and len(registered_paths(m)) == 1


def test_git_failures_during_resolution_are_typed(repo, root, tmp_path):
    fake = make_fake_git(tmp_path, '''
        if [ "$SUB" = worktree ] && [ "$SUB2" = list ]; then echo "fatal: list broke" >&2; exit 9; fi''')
    m = WorktreeManager(repo, root, git_executable=fake)
    with pytest.raises(GitCommandError) as info:
        m.create(rid(), "modular")
    assert info.value.details["returncode"] == 9 and reservations(m) == []


# --- 7. cleanup: exact path, git only, never broader -------------------------------------------------------------------------------------------------

def test_cleanup_removes_exactly_one_worktree_and_nothing_else(mgr):
    sibling_dir = mgr.root / "sibling-dir"
    write(sibling_dir / "keep.txt", "keep\n")
    other = mgr.create(rid(1), "modular")
    wt = mgr.create(rid(2), "modular")
    write(wt.path / "src/pocketcart/untracked.py", "u = 1\n")            # untracked changes need --force
    (wt.path / "pyproject.toml").write_text("modified\n")
    with forbid_recursive_deletes() as unlinked:
        mgr.remove(wt)
    assert not wt.path.exists() and wt.removed and os.path.realpath(wt.path) not in registered_paths(mgr)
    assert (sibling_dir / "keep.txt").read_text() == "keep\n"
    assert (other.path / "pyproject.toml").exists() and mgr.root.is_dir()
    assert len(unlinked) == 1 and unlinked[0].endswith(f"{rid(2)}.json")   # only the run's own reservation file
    mgr.remove(wt)                                                          # idempotent
    mgr.remove(other)


def test_cleanup_runs_git_worktree_remove_force_with_the_exact_path(repo, root, tmp_path):
    log = tmp_path / "calls.log"
    fake = make_fake_git(tmp_path, f'echo "$@" >> "{log}"')
    m = WorktreeManager(repo, root, git_executable=fake)
    wt = m.create(rid(), "modular")
    log.write_text("")
    m.remove(wt)
    removes = [l for l in log.read_text().splitlines() if " worktree remove " in l]
    assert len(removes) == 1 and removes[0].endswith(f"worktree remove --force {wt.path}")
    assert not any(" prune" in l for l in log.read_text().splitlines())    # no broad prune on the happy path


def test_cleanup_failure_preserves_the_worktree_and_siblings_and_can_be_retried(repo, root, tmp_path):
    fake = make_fake_git(tmp_path, '''
        if [ "$SUB" = worktree ] && [ "$SUB2" = remove ]; then echo "fatal: cannot remove" >&2; exit 3; fi''')
    m = WorktreeManager(repo, root, git_executable=fake)
    sibling = root / "sibling-dir"
    write(sibling / "keep.txt", "keep\n")
    neighbour = m.create(rid(1), "modular")
    wt = m.create(rid(2), "modular")
    write(wt.path / "src/pocketcart/precious.txt", "investigate me\n")
    with forbid_recursive_deletes():
        with pytest.raises(CleanupError) as info:
            m.remove(wt)
    assert info.value.classification == "cleanup_failed" and info.value.manifest_outcome == "runner_error"
    assert (wt.path / "src/pocketcart/precious.txt").read_text() == "investigate me\n"
    assert (sibling / "keep.txt").exists() and (neighbour.path / "pyproject.toml").exists() and root.is_dir()
    assert os.path.realpath(wt.path) in registered_paths(m) and not wt.removed
    assert f"{rid(2)}.json" in reservations(m)
    m.git = REAL_GIT                                                        # the failure clears; retry works
    m.remove(wt)
    assert not wt.path.exists() and sibling.exists()
    m.remove(neighbour)


@pytest.mark.parametrize("forged", ["root", "root.parent", "inside", "dest", "sibling", "repo", "slash", "tmp"])
def test_forged_or_broadened_cleanup_paths_are_refused_and_nothing_is_deleted(mgr, repo, tmp_path, forged):
    """Regression for the P0.3 incident, which called rmtree(dest.parent.parent) and destroyed the worktree root.

    Whatever path a caller records, cleanup deletes nothing except the one registered worktree it owns.
    """
    wt = mgr.create(rid(), "modular")
    dest = wt.path / ".futurefork-evaluator" / "partial_refund"
    write(dest / "test_pack.py", "oracle = 1\n")
    assert dest.parent.parent == wt.path                                    # the exact shape of the old bug
    sibling = mgr.root / "sibling-dir"
    write(sibling / "keep.txt", "keep\n")
    target = {"root": mgr.root, "root.parent": mgr.root.parent, "inside": wt.path / "src", "dest": dest.parent,
              "sibling": sibling, "repo": repo, "slash": Path("/"), "tmp": tmp_path}[forged]
    bogus = dataclasses.replace(wt, path=target)
    with forbid_recursive_deletes():
        with pytest.raises(CleanupError):
            mgr.remove(bogus)
    for survivor in (wt.path / "pyproject.toml", dest / "test_pack.py", sibling / "keep.txt", repo / "ORCHESTRATOR.md"):
        assert survivor.exists(), survivor
    assert mgr.root.is_dir() and mgr.root.parent.is_dir()
    assert os.path.realpath(wt.path) in registered_paths(mgr)
    mgr.remove(wt)                                                          # the legitimate handle still works
    assert not wt.path.exists() and (sibling / "keep.txt").exists()


def test_an_unregistered_directory_at_the_recorded_path_is_never_deleted(mgr):
    imposter = mgr.root / rid()
    write(imposter / "user-data.txt", "important\n")
    stub = mgr_stub(mgr, rid())
    with forbid_recursive_deletes():
        with pytest.raises(CleanupError, match="not a registered worktree"):
            mgr.remove(stub)
    assert (imposter / "user-data.txt").read_text() == "important\n"


def mgr_stub(manager: WorktreeManager, run_id: str) -> wtmod.Worktree:
    return wtmod.Worktree(run_id, manager.path_for(run_id), manager.repo, "modular", "refs/heads/modular", "0" * 40, "0" * 40)


def test_a_symlink_at_the_recorded_path_is_refused(mgr, tmp_path):
    outside = tmp_path / "outside"
    write(outside / "keep.txt", "keep\n")
    os.symlink(outside, mgr.root / rid())
    with forbid_recursive_deletes():
        with pytest.raises(CleanupError):
            mgr.remove(mgr_stub(mgr, rid()))
    assert (outside / "keep.txt").exists()


def test_a_recorded_path_that_disagrees_with_the_run_id_is_refused(mgr):
    a, b = mgr.create(rid(1), "modular"), mgr.create(rid(2), "modular")
    with pytest.raises(CleanupError):
        mgr.remove(dataclasses.replace(a, path=b.path))
    assert a.path.exists() and b.path.exists()
    mgr.remove(a), mgr.remove(b)


def _refusing_remove_git(tmp_path: Path) -> str:
    return make_fake_git(tmp_path, '''
        if [ "$SUB" = worktree ] && [ "$SUB2" = remove ]; then echo "fatal: refusing" >&2; exit 1; fi''')


def test_missing_directory_is_pruned_only_when_git_names_exactly_this_worktree(repo, root, tmp_path):
    m = WorktreeManager(repo, root, git_executable=_refusing_remove_git(tmp_path))
    ours = m.create(rid(1), "modular")
    stale = tmp_path / "stale-elsewhere"
    git(repo, "worktree", "add", "-q", "--detach", str(stale), "modular")
    shutil.move(str(stale), str(stale) + ".gone")               # someone else's stale registration
    shutil.move(str(ours.path), str(ours.path) + ".gone")       # ours is missing too
    with pytest.raises(CleanupError, match="other worktrees"):
        m.remove(ours)
    registered = registered_paths(m)                            # nothing was pruned, theirs or ours
    assert os.path.realpath(ours.path) in registered and os.path.realpath(stale) in registered
    assert not ours.removed and f"{rid(1)}.json" in reservations(m)
    shutil.move(str(stale) + ".gone", str(stale))               # heal both, then clean up with real git
    shutil.move(str(ours.path) + ".gone", str(ours.path))
    m.git = REAL_GIT
    m.remove(ours)
    git(repo, "worktree", "remove", "--force", str(stale))


def test_a_lone_missing_directory_is_pruned_by_git_when_remove_refuses(repo, root, tmp_path):
    m = WorktreeManager(repo, root, git_executable=_refusing_remove_git(tmp_path))
    wt = m.create(rid(), "modular")
    shutil.move(str(wt.path), str(wt.path) + ".gone")
    m.remove(wt)
    assert os.path.realpath(wt.path) not in registered_paths(m) and Path(str(wt.path) + ".gone").exists()
    assert wt.removed and reservations(m) == []


def test_a_lone_missing_directory_is_removed_by_git_directly(mgr):
    wt = mgr.create(rid(), "modular")
    shutil.move(str(wt.path), str(wt.path) + ".gone")
    mgr.remove(wt)
    assert os.path.realpath(wt.path) not in registered_paths(mgr) and reservations(mgr) == []


def test_no_module_code_can_delete_trees_by_construction():
    source = Path(wtmod.__file__).read_text()
    code = source.split('"""', 2)[2]                                        # everything after the module docstring
    code = "\n".join(l for l in code.splitlines() if not l.lstrip().startswith("#"))
    for banned in ("rmtree", "shutil", "os.rmdir", "os.removedirs", "glob", "fnmatch", "os.walk", "rglob", "iterdir",
                   "shell=True", "os.system", "os.remove(", ".unlink(missing_ok"):
        assert banned not in code, banned
    assert len(re.findall(r"os\.unlink\(", code)) == 1                      # the single reservation-file release


# --- 8. context manager ---------------------------------------------------------------------------------------------------------------------------------

def test_context_manager_cleans_up_on_normal_exit(mgr):
    with mgr.worktree(rid(), "modular") as wt:
        assert wt.path.exists() and os.path.realpath(wt.path) in registered_paths(mgr)
    assert not wt.path.exists() and wt.removed and reservations(mgr) == [] and len(registered_paths(mgr)) == 1


def test_context_manager_cleans_up_on_exception_and_propagates_it(mgr):
    with pytest.raises(RuntimeError, match="experiment blew up"):
        with mgr.worktree(rid(), "modular") as wt:
            write(wt.path / "src/pocketcart/x.py", "x = 1\n")
            raise RuntimeError("experiment blew up")
    assert not wt.path.exists() and reservations(mgr) == []


def test_context_manager_cleans_up_on_keyboard_interrupt(mgr):
    with pytest.raises(KeyboardInterrupt):
        with mgr.worktree(rid(), "modular") as wt:
            raise KeyboardInterrupt
    assert not wt.path.exists() and reservations(mgr) == [] and len(registered_paths(mgr)) == 1


def test_explicit_retain_keeps_the_worktree_and_blocks_reuse_of_the_run_id(mgr, repo):
    with mgr.worktree(rid(), "modular") as wt:
        write(wt.path / "src/pocketcart/evidence.py", "failed = True\n")
        wt.retain("acceptance tests failed; keep for investigation")
    assert wt.retained and wt.retain_reason and not wt.removed
    assert (wt.path / "src/pocketcart/evidence.py").exists() and os.path.realpath(wt.path) in registered_paths(mgr)
    assert reservations(mgr) == [f"{rid()}.json"]
    with pytest.raises(RunIdInUseError):
        mgr.create(rid(), "modular")
    assert git(repo, "rev-parse", "modular") == wt.commit
    mgr.remove(wt)                                                          # explicit disposal later
    assert not wt.path.exists() and reservations(mgr) == []


def test_retain_requires_a_reason(mgr):
    with mgr.worktree(rid(), "modular") as wt:
        with pytest.raises(ValueError):
            wt.retain("")
    assert not wt.path.exists()


def test_retain_on_error_keeps_after_exceptions_but_not_after_interrupts_or_success(mgr):
    with pytest.raises(RuntimeError):
        with mgr.worktree(rid(1), "modular", retain_on_error=True) as kept:
            raise RuntimeError("fail")
    assert kept.retained and kept.path.exists() and "RuntimeError" in kept.retain_reason
    with mgr.worktree(rid(2), "modular", retain_on_error=True) as ok:
        pass
    assert not ok.path.exists()
    with pytest.raises(KeyboardInterrupt):
        with mgr.worktree(rid(3), "modular", retain_on_error=True) as interrupted:
            raise KeyboardInterrupt
    assert not interrupted.path.exists()
    mgr.remove(kept)


def test_cleanup_failure_inside_the_context_manager_preserves_the_worktree_and_chains_the_cause(repo, root, tmp_path):
    fake = make_fake_git(tmp_path, '''
        if [ "$SUB" = worktree ] && [ "$SUB2" = remove ]; then echo "fatal: locked" >&2; exit 5; fi''')
    m = WorktreeManager(repo, root, git_executable=fake)
    with pytest.raises(CleanupError) as info:
        with m.worktree(rid(), "modular") as wt:
            raise RuntimeError("original failure")
    chain, err = [], info.value
    while err is not None and err not in chain:
        chain.append(err)
        err = err.__cause__ or err.__context__
    assert any(isinstance(e, RuntimeError) and "original failure" in str(e) for e in chain), chain
    assert wt.path.exists() and os.path.realpath(wt.path) in registered_paths(m)
    m.git = REAL_GIT
    m.remove(wt)


def test_context_manager_exit_verifies_that_sources_did_not_move(mgr, repo):
    with pytest.raises(SourceChangedError):
        with mgr.worktree(rid(), "modular"):
            git(repo, "branch", "-f", "modular", "coupled")
    git(repo, "branch", "-f", "modular", "modular@{1}")


# --- errors map to P0.4 outcomes ---------------------------------------------------------------------------------------------------------------------------

def _all_error_classes():
    return [c for c in vars(wtmod).values() if isinstance(c, type) and issubclass(c, WorktreeError)]


def test_every_error_names_a_valid_infrastructure_manifest_outcome():
    classes = _all_error_classes()
    assert len(classes) >= 17
    candidate_side = {InvalidRefError, NotACommitError, DirtyCandidateError, CandidateContaminatedError}
    for cls in classes:
        outcome = Outcome(cls.manifest_outcome)                             # must be a real taxonomy value
        assert outcome_class(outcome) is OutcomeClass.INFRASTRUCTURE, cls
        assert (outcome is Outcome.CANDIDATE_INVALID) == (cls in candidate_side), cls
    assert len({c.classification for c in classes}) == len(classes)          # unambiguous


def test_no_error_can_be_recorded_as_a_candidate_experiment_failure():
    experimental = {Outcome.ACCEPTANCE_FAILED.value, Outcome.REGRESSION_FAILED.value, Outcome.COMPLETED.value,
                    Outcome.BUDGET_EXHAUSTED.value}
    assert not any(c.manifest_outcome in experimental for c in _all_error_classes())


# --- the real repository is never used ---------------------------------------------------------------------------------------------------------------------------

def test_fixtures_never_point_at_the_production_repository(mgr, repo, root):
    assert repo != ROOT and ROOT not in repo.parents and ROOT not in root.parents and mgr.repo != ROOT
    assert not str(root).startswith("/private/tmp/futurefork-p03")
    assert mgr.repo == Path(os.path.realpath(repo))
