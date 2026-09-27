"""Isolated Git execution: one detached, disposable worktree per run.

Guarantees (each is covered by tests/test_worktrees.py, which only ever uses temporary
repositories):

* The candidate ref is resolved to a full commit OID exactly once; the worktree is created from
  that OID, detached. The ref, the OID, and any `watch_refs` are re-read afterwards and any change
  raises `SourceChangedError`. This module never writes to refs.
* Each run gets its own directory directly under an explicit root that lies outside the source
  repository and every forbidden root (oracle / protected-test sources). Run ids are validated
  with the manifest's `RUN_ID_PATTERN`; paths are canonicalized and confined.
* Collisions (existing path, registered worktree, another holder of the same run id) are detected;
  an atomic `O_EXCL` reservation file lets exactly one concurrent creator win.
* Every Git call is an argv array with `shell=False`, a finite timeout, and bounded captured
  output. A timeout or interrupt kills the whole process group.
* Cleanup is `git worktree remove --force <exact recorded path>` and nothing else. There is no
  recursive deletion anywhere in this module, no globbing, and no manual fallback: if Git cannot
  remove the worktree, the path is left in place and `CleanupError` is raised. (The P0.3 incident
  came from `rmtree(dest.parent.parent)`.)

Errors carry a `manifest_outcome` naming the P0.4 outcome a runner should record: problems with
the candidate are `candidate_invalid`; everything else is `runner_error`, which must never be
counted against a candidate.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import signal
import stat
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Literal, Sequence

from .manifest import REF_PATTERN, RUN_ID_PATTERN

DEFAULT_GIT_TIMEOUT = 60.0
DEFAULT_ADD_TIMEOUT = 180.0
DEFAULT_MAX_OUTPUT_BYTES = 1_000_000
KILL_GRACE_SECONDS = 0.2
# Paths that must never be part of a candidate snapshot (oracle material).
DEFAULT_FORBIDDEN_TREE_PATHS = (".futurefork-evaluator", "scenarios", ".bob", "bob_sessions")
RESERVATIONS_DIR = ".reservations"

_OID = re.compile(r"[0-9a-f]{40}")
_RUN_ID = re.compile(RUN_ID_PATTERN)
_REF = re.compile(REF_PATTERN)


# --- typed errors ---------------------------------------------------------------------------------

class WorktreeError(Exception):
    """Base class. `classification` is stable text; `manifest_outcome` is a P0.4 Outcome value."""

    classification = "worktree_error"
    manifest_outcome = "runner_error"

    def __init__(self, message: str, **details: object) -> None:
        super().__init__(message)
        self.details = details


class InvalidIdError(WorktreeError):
    classification = "invalid_id"


class ConfinementError(WorktreeError):
    classification = "confinement"


class InvalidRefError(WorktreeError):
    classification = "invalid_ref"
    manifest_outcome = "candidate_invalid"


class NotACommitError(WorktreeError):
    classification = "not_a_commit"
    manifest_outcome = "candidate_invalid"


class DirtyCandidateError(WorktreeError):
    classification = "dirty_candidate"
    manifest_outcome = "candidate_invalid"


class CandidateContaminatedError(WorktreeError):
    classification = "candidate_contaminated"
    manifest_outcome = "candidate_invalid"


class CollisionError(WorktreeError):
    classification = "collision"


class PathCollisionError(CollisionError):
    classification = "collision_path_exists"


class RegisteredCollisionError(CollisionError):
    classification = "collision_registered_worktree"


class RunIdInUseError(CollisionError):
    classification = "collision_run_id_in_use"


class GitCommandError(WorktreeError):
    classification = "git_failure"


class WorktreeAddError(GitCommandError):
    classification = "git_worktree_add_failed"


class GitTimeoutError(WorktreeError):
    classification = "git_timeout"


class SourceChangedError(WorktreeError):
    classification = "source_changed"


class VerificationError(WorktreeError):
    classification = "verification_failed"


class CleanupError(WorktreeError):
    """The worktree could not be removed. The path is preserved, never deleted by other means."""

    classification = "cleanup_failed"


# --- results ----------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class GitResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    truncated: bool


@dataclass
class Worktree:
    run_id: str
    path: Path
    repo: Path
    ref: str
    full_ref: str
    commit: str
    tree: str
    source_dirty: bool = False
    dirty_source_paths: tuple[str, ...] = ()
    retained: bool = False
    retain_reason: str | None = None
    removed: bool = False
    watch_refs: dict[str, str | None] = field(default_factory=dict)

    def retain(self, reason: str) -> None:
        """Keep this worktree on disk for investigation (e.g. a failed experimental run)."""
        if not reason:
            raise ValueError("retain() needs a reason")
        self.retained = True
        self.retain_reason = reason


def default_worktree_root() -> Path:
    """Per-user root under the OS temp directory (outside any repository)."""
    return Path(tempfile.gettempdir()) / f"futurefork-worktrees-{os.getuid()}"


# --- process execution ----------------------------------------------------------------------------------------

class _Capture(threading.Thread):
    """Drain a pipe, keeping at most `limit` bytes but always reading to EOF so the child never blocks."""

    def __init__(self, stream, limit: int) -> None:
        super().__init__(daemon=True)
        self._stream, self._limit = stream, limit
        self.data = bytearray()
        self.truncated = False

    def run(self) -> None:
        try:
            while chunk := self._stream.read(65536):
                room = self._limit - len(self.data)
                if room > 0:
                    self.data += chunk[:room]
                if len(chunk) > max(room, 0):
                    self.truncated = True
        except (OSError, ValueError):
            pass


def _kill_group(proc: subprocess.Popen) -> None:
    """Terminate, then kill, the whole process group of `proc`.

    `proc` has not been reaped yet, so its pid (== its process group id, because it was started
    in a new session) cannot have been recycled.
    """
    for sig in (signal.SIGTERM, signal.SIGKILL):
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, sig)
        if sig == signal.SIGTERM:
            time.sleep(KILL_GRACE_SECONDS)
    with contextlib.suppress(Exception):
        proc.wait(timeout=5)


class WorktreeManager:
    def __init__(
        self,
        repo: Path | str,
        root: Path | str,
        *,
        forbidden_roots: Sequence[Path | str] = (),
        git_executable: str = "git",
        git_timeout: float = DEFAULT_GIT_TIMEOUT,
        add_timeout: float = DEFAULT_ADD_TIMEOUT,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
        dirty_source: Literal["error", "record"] = "error",
        forbidden_tree_paths: Sequence[str] = DEFAULT_FORBIDDEN_TREE_PATHS,
    ) -> None:
        if git_timeout <= 0 or add_timeout <= 0 or max_output_bytes <= 0:
            raise ValueError("timeouts and max_output_bytes must be positive")
        if dirty_source not in ("error", "record"):
            raise ValueError("dirty_source must be 'error' or 'record'")
        self.git = git_executable
        self.git_timeout, self.add_timeout = git_timeout, add_timeout
        self.max_output_bytes = max_output_bytes
        self.dirty_source = dirty_source
        self.forbidden_tree_paths = tuple(forbidden_tree_paths)
        self._env = self._clean_env()

        self.repo = Path(os.path.realpath(repo))
        if not self.repo.is_dir():
            raise ConfinementError(f"repository does not exist: {repo}")
        self.common_dir = self._common_dir()
        self.forbidden_roots = tuple(Path(os.path.realpath(p)) for p in (self.repo, *forbidden_roots))
        self.root = self._prepare_root(Path(root))

    # -- configuration -----------------------------------------------------------------------------------

    @staticmethod
    def _clean_env() -> dict[str, str]:
        keep = {k: os.environ[k] for k in ("PATH", "HOME", "TMPDIR", "USER", "LOGNAME") if k in os.environ}
        # No GIT_DIR / GIT_WORK_TREE / GIT_INDEX_FILE etc. are inherited; nothing may prompt.
        return {**keep, "LC_ALL": "C", "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}

    def _common_dir(self) -> Path:
        out = self._git(["rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=self.repo).stdout.strip()
        return Path(os.path.realpath(out))

    def _prepare_root(self, root: Path) -> Path:
        if not root.is_absolute():
            raise ConfinementError(f"worktree root must be an absolute path: {root}")
        if any(ord(c) < 32 or ord(c) == 127 for c in str(root)):
            raise ConfinementError("worktree root contains control characters")
        canonical = Path(os.path.realpath(root))
        if canonical == Path(canonical.anchor):
            raise ConfinementError("worktree root cannot be the filesystem root")
        for forbidden in self.forbidden_roots:
            if canonical == forbidden or forbidden in canonical.parents or canonical in forbidden.parents:
                raise ConfinementError(
                    f"worktree root {canonical} overlaps {forbidden} (repository, oracle, or protected source)"
                )
        if self.common_dir == canonical or self.common_dir in canonical.parents:
            raise ConfinementError("worktree root cannot live inside the repository's git directory")
        try:
            canonical.mkdir(mode=0o700, parents=True, exist_ok=True)
        except (FileExistsError, NotADirectoryError) as exc:
            raise ConfinementError(f"worktree root (or a parent) is not a directory: {canonical}") from exc
        st = os.lstat(canonical)
        if not stat.S_ISDIR(st.st_mode):
            raise ConfinementError(f"worktree root is not a directory: {canonical}")
        if st.st_uid != os.getuid():
            raise ConfinementError("worktree root is not owned by the current user")
        if st.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise ConfinementError("worktree root must not be group- or world-writable")
        res = canonical / RESERVATIONS_DIR
        if res.is_symlink():
            raise ConfinementError("reservations directory must not be a symlink")
        res.mkdir(mode=0o700, exist_ok=True)
        return canonical

    # -- git execution -----------------------------------------------------------------------------------------

    def _git(self, args: Sequence[str], *, cwd: Path, timeout: float | None = None,
             ok: Sequence[int] = (0,), error: type[GitCommandError] = GitCommandError) -> GitResult:
        argv = [self.git, "-c", f"core.hooksPath={os.devnull}", "-c", "core.fsmonitor=false", *args]
        timeout = self.git_timeout if timeout is None else timeout
        try:
            proc = subprocess.Popen(
                argv, cwd=cwd, env=self._env, shell=False, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
            )
        except OSError as exc:
            raise error(f"cannot execute git ({self.git}): {exc}", argv=argv) from exc
        out, err = _Capture(proc.stdout, self.max_output_bytes), _Capture(proc.stderr, self.max_output_bytes)
        out.start(), err.start()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_group(proc)
            raise GitTimeoutError(f"git timed out after {timeout}s: {' '.join(args)}", argv=argv, timeout=timeout) from None
        except BaseException:  # KeyboardInterrupt and friends: never leave git running
            _kill_group(proc)
            raise
        out.join(timeout=5), err.join(timeout=5)
        proc.stdout.close(), proc.stderr.close()
        result = GitResult(tuple(argv), proc.returncode, out.data.decode("utf-8", "replace"),
                           err.data.decode("utf-8", "replace"), out.truncated or err.truncated)
        if result.returncode not in ok:
            raise error(
                f"git {' '.join(args[:2])} failed with exit status {result.returncode}: {result.stderr.strip()[:500]}",
                argv=argv, returncode=result.returncode, stderr=result.stderr[:2000],
            )
        return result

    # -- ids and paths ---------------------------------------------------------------------------------------------

    @staticmethod
    def validate_run_id(run_id: object) -> str:
        if not isinstance(run_id, str) or len(run_id) > 200 or not _RUN_ID.fullmatch(run_id):
            raise InvalidIdError(f"invalid run id: {run_id!r}")
        return run_id

    def path_for(self, run_id: str) -> Path:
        """Canonical, confined path for a run id. Does not touch the filesystem."""
        run_id = self.validate_run_id(run_id)
        path = self.root / run_id
        if path.parent != self.root or os.path.commonpath([self.root, path]) != str(self.root):
            raise ConfinementError(f"path escapes the worktree root: {path}")
        return path

    def _reservation_path(self, run_id: str) -> Path:
        return self.root / RESERVATIONS_DIR / f"{run_id}.json"

    # -- refs ------------------------------------------------------------------------------------------------------------

    def _rev_parse(self, spec: str) -> str | None:
        r = self._git(["rev-parse", "--verify", "--quiet", "--end-of-options", spec], cwd=self.repo, ok=(0, 1))
        return r.stdout.strip() if r.returncode == 0 else None

    def resolve(self, ref: str) -> tuple[str, str, str]:
        """(full ref name, commit OID, tree OID). Branches win over tags for short names."""
        if not isinstance(ref, str) or not _REF.fullmatch(ref):
            raise InvalidRefError(f"not a valid ref name: {ref!r}")
        full_names = [ref] if ref.startswith("refs/") else [f"refs/heads/{ref}", f"refs/tags/{ref}"]
        for full in full_names:
            if self._rev_parse(full) is None:
                continue
            commit = self._rev_parse(f"{full}^{{commit}}")
            if commit is None:
                raise NotACommitError(f"{full} does not point to a commit", ref=full)
            tree = self._rev_parse(f"{commit}^{{tree}}")
            if not commit or not _OID.fullmatch(commit) or not tree or not _OID.fullmatch(tree):
                raise GitCommandError(f"unexpected object ids for {full}: {commit!r} {tree!r}")
            return full, commit, tree
        raise InvalidRefError(f"ref not found: {ref}", ref=ref)

    def ref_state(self, refs: Sequence[str]) -> dict[str, str | None]:
        """Current OID (or None) of each ref, read without side effects."""
        state: dict[str, str | None] = {}
        for ref in refs:
            full = ref if ref.startswith("refs/") else f"refs/heads/{ref}"
            state[ref] = self._rev_parse(full)
        return state

    # -- registered worktrees --------------------------------------------------------------------------------------------

    def registered(self) -> list[dict[str, str]]:
        out = self._git(["worktree", "list", "--porcelain"], cwd=self.repo).stdout
        blocks: list[dict[str, str]] = []
        for chunk in out.strip().split("\n\n"):
            if not chunk.strip():
                continue
            entry: dict[str, str] = {}
            for line in chunk.splitlines():
                key, _, value = line.partition(" ")
                entry[key] = value
            if "worktree" in entry:
                entry["realpath"] = os.path.realpath(entry["worktree"])
                blocks.append(entry)
        return blocks

    def _is_registered(self, path: Path) -> bool:
        target = os.path.realpath(path)
        return any(e["realpath"] == target for e in self.registered())

    def _dirty_source_worktrees(self, full_ref: str) -> dict[str, tuple[str, ...]]:
        """Existing worktrees that have exactly this candidate branch checked out and are dirty.

        Unrelated changes elsewhere (e.g. an orchestrator checkout on `main`, or detached
        experiment worktrees) are deliberately ignored.
        """
        dirty: dict[str, tuple[str, ...]] = {}
        for entry in self.registered():
            if entry.get("branch") != full_ref or "bare" in entry:
                continue
            path = Path(entry["worktree"])
            if not path.is_dir():
                continue
            status = self._git(["status", "--porcelain", "--untracked-files=all"], cwd=path).stdout
            if status.strip():
                dirty[str(path)] = tuple(line for line in status.splitlines()[:20])
        return dirty

    # -- create ----------------------------------------------------------------------------------------------------------

    def create(self, run_id: str, candidate_ref: str, *, watch_refs: Sequence[str] = ()) -> Worktree:
        path = self.path_for(run_id)
        full_ref, commit, tree = self.resolve(candidate_ref)          # the one and only ref resolution
        watched = self.ref_state([full_ref, *watch_refs])
        self._check_candidate_tree(commit)
        dirty = self._dirty_source_worktrees(full_ref)
        if dirty and self.dirty_source == "error":
            raise DirtyCandidateError(
                f"candidate {full_ref} is checked out in a dirty worktree: {sorted(dirty)}", worktrees=sorted(dirty))

        self._reserve(run_id, commit, candidate_ref)
        try:
            self._check_free(path)
        except BaseException:
            self._release(run_id)          # we just took this reservation; the collision is someone else's path
            raise
        try:
            self._git(["worktree", "add", "--detach", "--", str(path), commit], cwd=self.repo,
                      timeout=self.add_timeout, error=WorktreeAddError)
        except BaseException:
            try:
                self._abort_creation(path, run_id)     # Git's own removal only; may raise CleanupError
            finally:
                self._release_if_unused(run_id, path)  # an unregistered leftover keeps the reservation
            raise
        wt = Worktree(run_id, path, self.repo, candidate_ref, full_ref, commit, tree,
                      source_dirty=bool(dirty), dirty_source_paths=tuple(sorted(dirty)), watch_refs=watched)
        try:
            self._verify_new(wt)
        except BaseException:
            self._remove_exact(wt)          # a CleanupError here chains the verification failure as its cause
            self._release(run_id)
            raise
        return wt

    def _check_candidate_tree(self, commit: str) -> None:
        if not self.forbidden_tree_paths:
            return
        out = self._git(["ls-tree", "--name-only", commit, "--", *self.forbidden_tree_paths], cwd=self.repo).stdout
        if out.strip():
            raise CandidateContaminatedError(
                f"candidate commit {commit} contains oracle/orchestrator paths: {out.split()}", paths=out.split())

    def _check_free(self, path: Path) -> None:
        if os.path.lexists(path):
            raise PathCollisionError(f"path already exists: {path}", path=str(path))
        if self._is_registered(path):
            raise RegisteredCollisionError(f"a git worktree is already registered at {path}", path=str(path))

    def _verify_new(self, wt: Worktree) -> None:
        head = self._git(["rev-parse", "HEAD"], cwd=wt.path).stdout.strip()
        if head != wt.commit:
            raise VerificationError(f"worktree HEAD {head} != resolved commit {wt.commit}")
        if self._git(["symbolic-ref", "-q", "HEAD"], cwd=wt.path, ok=(0, 1)).returncode == 0:
            raise VerificationError("worktree HEAD is not detached")
        if self._git(["rev-parse", "HEAD^{tree}"], cwd=wt.path).stdout.strip() != wt.tree:
            raise VerificationError("worktree tree differs from the candidate tree")
        status = self._git(["status", "--porcelain", "--untracked-files=all"], cwd=wt.path).stdout
        if status.strip():
            raise VerificationError(f"new worktree is not clean: {status.strip()[:300]}")
        self.verify_sources(wt)

    def verify_sources(self, wt: Worktree) -> None:
        """Raise SourceChangedError if the candidate ref or any watched ref moved since creation."""
        now = self.ref_state(list(wt.watch_refs))
        moved = {r: (wt.watch_refs[r], now[r]) for r in wt.watch_refs if now[r] != wt.watch_refs[r]}
        if moved:
            raise SourceChangedError(f"source refs changed while the worktree existed: {moved}", moved=moved)
        # An annotated tag's raw value is the tag object, so compare the *peeled* commit.
        current = self._rev_parse(f"{wt.full_ref}^{{commit}}")
        if current != wt.commit:
            raise SourceChangedError(
                f"candidate ref {wt.full_ref} now resolves to {current}, not the recorded {wt.commit}",
                moved={wt.full_ref: (wt.commit, current)})

    # -- reservation (atomic, per run id) ------------------------------------------------------------------------------------

    def _reserve(self, run_id: str, commit: str, ref: str) -> None:
        reservation = self._reservation_path(run_id)
        payload = json.dumps({"run_id": run_id, "pid": os.getpid(), "commit": commit, "ref": ref,
                              "reserved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, sort_keys=True)
        try:
            fd = os.open(reservation, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            holder = ""
            with contextlib.suppress(OSError):
                holder = reservation.read_text()[:300]
            raise RunIdInUseError(f"run id {run_id} is already reserved: {holder}", run_id=run_id) from None
        with os.fdopen(fd, "w") as handle:
            handle.write(payload)

    def _release(self, run_id: str) -> None:
        """Remove exactly this run's reservation file (one file, exact path)."""
        with contextlib.suppress(FileNotFoundError):
            os.unlink(self._reservation_path(run_id))

    def _release_if_unused(self, run_id: str, path: Path) -> None:
        if not os.path.lexists(path):
            self._release(run_id)

    def _abort_creation(self, path: Path, run_id: str) -> None:
        """`git worktree add` failed but left something behind: try Git's own removal, never more."""
        stub = Worktree(run_id, path, self.repo, "", "", "", "")
        if self._is_registered(path):
            self._remove_exact(stub)
            self._release(run_id)
        # An unregistered leftover directory is not ours to delete: keep it and the reservation.

    # -- cleanup ---------------------------------------------------------------------------------------------------------------------

    def remove(self, wt: Worktree) -> None:
        """Remove `wt` with `git worktree remove --force <exact path>`; raise CleanupError on failure."""
        if wt.removed:
            return
        self._remove_exact(wt)
        wt.removed = True
        self._release(wt.run_id)

    def _validated_recorded_path(self, wt: Worktree) -> Path:
        """The recorded path must be exactly what path_for(run_id) yields, unchanged and unlinked."""
        try:
            expected = self.path_for(wt.run_id)
        except WorktreeError as exc:
            raise CleanupError(f"refusing to clean up: {exc}", path=str(wt.path)) from exc
        if Path(wt.path) != expected:
            raise CleanupError(f"refusing to clean up: recorded path {wt.path} is not {expected}", path=str(wt.path))
        if expected == self.root or expected in self.forbidden_roots or self.repo in expected.parents:
            raise CleanupError("refusing to clean up a root or repository path", path=str(expected))
        if expected.is_symlink():
            raise CleanupError("refusing to clean up a symlink", path=str(expected))
        return expected

    def _remove_exact(self, wt: Worktree) -> None:
        path = self._validated_recorded_path(wt)
        registered = self._is_registered(path)
        if not registered and os.path.lexists(path):
            raise CleanupError(
                f"{path} exists but is not a registered worktree; refusing to delete it (no manual removal)", path=str(path))
        if registered:
            try:
                self._git(["worktree", "remove", "--force", str(path)], cwd=self.repo)
            except (GitTimeoutError, GitCommandError) as exc:
                if os.path.lexists(path):
                    raise CleanupError(f"git worktree remove failed; {path} preserved: {exc}", path=str(path)) from exc
                # The directory is already gone and Git refused to drop the record: prune, but only
                # if Git's own dry run names this worktree and nothing else.
                self._prune_only_ours(path)
        if os.path.lexists(path) or self._is_registered(path):
            raise CleanupError(f"worktree {path} is still present after removal; preserved", path=str(path))

    def _prune_only_ours(self, path: Path) -> None:
        """The directory is already gone. Prune only if Git's dry run names exactly this worktree."""
        dry = self._git(["worktree", "prune", "--dry-run", "--verbose"], cwd=self.repo)
        names = re.findall(r"^Removing worktrees/(\S+):", dry.stdout + "\n" + dry.stderr, re.M)  # Git reports on stderr
        if not names:
            return
        ours = []
        for name in names:
            gitdir_file = self.common_dir / "worktrees" / name / "gitdir"
            with contextlib.suppress(OSError):
                recorded = os.path.realpath(gitdir_file.read_text().strip())
                if recorded == os.path.realpath(path / ".git"):
                    ours.append(name)
        if len(ours) != len(names):
            raise CleanupError("prune would also remove other worktrees' records; not pruning", would_remove=names)
        self._git(["worktree", "prune"], cwd=self.repo, error=CleanupError)

    # -- context manager ------------------------------------------------------------------------------------------------------

    @contextlib.contextmanager
    def worktree(self, run_id: str, candidate_ref: str, *, watch_refs: Sequence[str] = (),
                 retain_on_error: bool = False) -> Iterator[Worktree]:
        """Create a worktree, yield it, and always clean it up (normal exit, exception, KeyboardInterrupt).

        Call `wt.retain(reason)` inside the block (or pass `retain_on_error=True`) to keep the
        directory for investigation; a retained worktree keeps its reservation so the run id
        cannot be reused. Source refs are re-verified on exit.
        """
        wt = self.create(run_id, candidate_ref, watch_refs=watch_refs)
        try:
            yield wt
        except Exception as exc:
            if retain_on_error and not wt.retained:
                wt.retain(f"retained after {type(exc).__name__}")
            raise
        finally:
            try:
                if not wt.retained:
                    self.remove(wt)
            finally:
                self.verify_sources(wt)
