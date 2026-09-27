"""The operator-driven `futurefork` runner: prepare a worktree for Bob, finalize its result.

There is no Bob API, so the workflow is honestly two operator-driven stages instead of one
atomic `futurefork run`:

  prepare  -- validate the candidate and scenario, create a *retained* detached worktree (via
              `WorktreeManager`), write the public task packet, and print the worktree path for
              the operator to open in Bob IDE. The protected pack is never copied, mounted, or
              otherwise exposed here. If the candidate ref is invalid or `setup_command` fails,
              there is no agent work to wait for, so `prepare` writes a terminal manifest itself
              (`candidate_invalid` / `setup_failed`).
  finalize -- called only after the Bob task has ended, with its real `--task-id`. Freezes the
              patch, verifies the protected pack against `PACKS.json` and mounts it only now,
              runs regression then protected tests under the scenario's limits, re-verifies the
              mounted pack afterward, writes the full evidence bundle, builds a strict
              `RunManifest` (via `futurefork.manifest`, never hand-built JSON), and removes the
              worktree through `WorktreeManager.remove` (exact recorded path only).

Outcomes never lie in either direction: an infrastructure or tooling failure is `runner_error`,
never folded into `regression_failed`/`acceptance_failed`; a compromised protected pack is always
`oracle_tampered`, never a candidate verdict, regardless of what the tests appeared to show.

Resume: finalize is safe to re-run on a run that was prepared but never reached `manifest.json`
(a crash, Ctrl-C, or an aborted attempt) — every artifact it writes before the manifest is a plain
overwrite, and the worktree is untouched until the very end, so simply invoking finalize again
with the same `--run-id` starts that evaluation over.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from . import manifest as mf
from . import testpack
from .scenario import SCENARIO_ID_PATTERN, Scenario, load_scenario, scenario_sha256
from .worktrees import CleanupError, WorktreeError, WorktreeManager, Worktree, _kill_group

_NAME_RE = re.compile(SCENARIO_ID_PATTERN)
STATE_FILE = "state.json"
MANIFEST_FILE = "manifest.json"


# --- CLI-level errors (never a manifest outcome: nothing has been decided about any candidate) ---------

class RunnerError(Exception):
    """A usage/precondition problem: no run (or an incomplete one) exists to reason about."""


class RunCollisionError(RunnerError):
    pass


class RunNotFoundError(RunnerError):
    pass


class RunAlreadyFinalizedError(RunnerError):
    pass


class InvalidNameError(RunnerError):
    pass


# --- configuration ---------------------------------------------------------------------------------------

@dataclass(frozen=True)
class RunnerConfig:
    repo: Path            # the FutureFork project root (source of candidate refs and scenarios/)
    runs_root: Path       # e.g. <repo>/artifacts/runs
    worktree_root: Path   # WorktreeManager root; must be outside repo/scenarios
    git_executable: str = "git"


def default_config(repo: Path | None = None) -> RunnerConfig:
    from .worktrees import default_worktree_root

    repo = Path(repo) if repo is not None else Path(__file__).resolve().parents[1]
    return RunnerConfig(repo=repo, runs_root=repo / "artifacts" / "runs", worktree_root=default_worktree_root())


def _packs_json(config: RunnerConfig) -> Path:
    return config.repo / "scenarios" / "demo" / "protected-tests" / "PACKS.json"


def _pack_source(config: RunnerConfig, scenario: Scenario) -> Path:
    return config.repo / scenario.protected_tests.source


def _worktree_manager(config: RunnerConfig) -> WorktreeManager:
    return WorktreeManager(config.repo, config.worktree_root, git_executable=config.git_executable)


# --- ids and paths -----------------------------------------------------------------------------------------

def generate_run_id(candidate_name: str, scenario_id: str, now: datetime | None = None) -> str:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    return f"{now.strftime('%Y%m%dT%H%M%SZ')}-{candidate_name}-{scenario_id}"


def _run_dir(config: RunnerConfig, run_id: str) -> Path:
    if not re.fullmatch(mf.RUN_ID_PATTERN, run_id):
        raise InvalidNameError(f"not a valid run id: {run_id!r}")
    return config.runs_root / run_id


# --- generic, limited command execution (argv array, shell=False, timeout + process-group kill) -----------

class _Capture(threading.Thread):
    """Drain a pipe, keeping at most `limit` bytes but always reading to EOF, and separately
    tracking the true total byte count even past that cap (so budget checks stay honest)."""

    def __init__(self, stream, limit: int) -> None:
        super().__init__(daemon=True)
        self._stream, self._limit = stream, limit
        self.data = bytearray()
        self.total = 0
        self.truncated = False

    def run(self) -> None:
        try:
            while chunk := self._stream.read(65536):
                self.total += len(chunk)
                room = self._limit - len(self.data)
                if room > 0:
                    self.data += chunk[:room]
                if len(chunk) > max(room, 0):
                    self.truncated = True
        except (OSError, ValueError):
            pass


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int | None       # None means it was killed for a timeout
    stdout: str
    stderr: str
    truncated: bool
    total_bytes: int             # true combined byte count seen, even beyond what was kept on disk
    timed_out: bool
    duration_seconds: float


def _in_allowlist(command: Sequence[str], allowlist: Sequence[Sequence[str]]) -> bool:
    return any(list(command[: len(prefix)]) == list(prefix) for prefix in allowlist)


def run_limited_command(command: Sequence[str], *, cwd: Path, timeout: float, max_output_bytes: int) -> CommandResult:
    """Run `command` (argv, shell=False) under a wall timeout and a bounded, fully-drained capture.

    On timeout, the whole process group is killed (same discipline as `worktrees._kill_group`).
    Never raises for a non-zero exit or a timeout; the caller decides what that means.
    """
    env = {k: os.environ[k] for k in ("PATH", "HOME", "TMPDIR", "USER", "LOGNAME") if k in os.environ}
    env["LC_ALL"] = "C"
    started = time.monotonic()
    proc = subprocess.Popen(
        list(command), cwd=cwd, env=env, shell=False, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
    )
    out, err = _Capture(proc.stdout, max_output_bytes), _Capture(proc.stderr, max_output_bytes)
    out.start(), err.start()
    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_group(proc)
    except BaseException:
        _kill_group(proc)
        raise
    out.join(timeout=5), err.join(timeout=5)
    proc.stdout.close(), proc.stderr.close()
    duration = time.monotonic() - started
    return CommandResult(
        tuple(command), None if timed_out else proc.returncode,
        out.data.decode("utf-8", "replace"), err.data.decode("utf-8", "replace"),
        out.truncated or err.truncated, out.total + err.total, timed_out, duration,
    )


# --- pytest summary parsing --------------------------------------------------------------------------------------

_SUMMARY_RE = re.compile(r"(\d+)\s+(passed|failed|errors?|skipped|xfailed|xpassed)")


def parse_pytest_summary(stdout: str) -> dict[str, int] | None:
    """Best-effort parse of pytest's own final summary line. None if nothing recognizable is there."""
    matches = _SUMMARY_RE.findall(stdout[-4000:])
    if not matches:
        return None
    counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    for n, kind in matches:
        n = int(n)
        if kind == "passed":
            counts["passed"] += n
        elif kind == "failed":
            counts["failed"] += n
        elif kind in ("error", "errors"):
            counts["errors"] += n
        elif kind == "skipped":
            counts["skipped"] += n
    return counts


def classify_test_run(result: CommandResult) -> tuple[mf.TestState, dict[str, int] | None]:
    """(state, counts). counts is None when we could not get a clean, trustworthy signal."""
    if result.timed_out:
        return mf.TestState.ERROR, None
    counts = parse_pytest_summary(result.stdout)
    if counts is None or result.returncode not in (0, 1):
        return mf.TestState.ERROR, counts
    if result.returncode == 0:
        if counts["passed"] >= 1 and counts["failed"] == 0 and counts["errors"] == 0:
            return mf.TestState.PASSED, counts
        return mf.TestState.ERROR, counts  # exit 0 without a clean "N passed" is not trustworthy
    if counts["failed"] >= 1:
        return mf.TestState.FAILED, counts
    return mf.TestState.ERROR, counts


def _test_run(state: mf.TestState, command: list[str], result: CommandResult | None,
              counts: dict[str, int] | None, results_artifact: str | None) -> mf.TestRun:
    kwargs = dict(state=state, command=command)
    if result is not None and not result.timed_out:
        kwargs["returncode"] = result.returncode
    if counts is not None:
        kwargs.update(passed=counts["passed"], failed=counts["failed"], errors=counts["errors"], skipped=counts["skipped"])
        kwargs["results_artifact"] = results_artifact
    return mf.TestRun(**kwargs)


# --- task packet -------------------------------------------------------------------------------------------------

def _json_block(value: dict) -> str:
    """Deterministic (sorted-key) pretty JSON, indented for a Markdown bullet's continuation."""
    text = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True)
    return "\n".join("  " + line for line in text.splitlines())


def _render_endpoint(e) -> str:
    """Every PUBLIC field of one endpoint: method, path, summary, request, response, errors.
    Never protected_tests/mount/pack/oracle content — Endpoint carries none of that."""
    lines = [f"- `{e.method} {e.path}` — {e.summary}"]
    if e.request:
        lines += ["", "  Request:", "  ```json", _json_block(e.request), "  ```"]
    if e.response:
        lines += ["", "  Response:", "  ```json", _json_block(e.response), "  ```"]
    if e.errors:
        lines += ["", "  Errors:", "  ```json", _json_block({str(k): v for k, v in sorted(e.errors.items())}), "  ```"]
    return "\n".join(lines)


def render_task_packet(scenario: Scenario, candidate_name: str, commit: str) -> str:
    criteria = "\n".join(f"{i}. {c}" for i, c in enumerate(scenario.public_acceptance_criteria, 1))
    endpoints = "\n\n".join(_render_endpoint(e) for e in scenario.public_interface.endpoints)
    rules = "\n".join(f"- {r}" for r in scenario.public_interface.rules)
    commands = ", ".join("`" + " ".join(c) + "`" for c in scenario.command_allowlist)
    paths = ", ".join(f"`{p}`" for p in scenario.editable_paths)
    return f"""# FutureFork task packet — {scenario.id}

You are implementing one hypothetical future requirement in an isolated FutureFork experiment.

- Candidate: `{candidate_name}`
- Scenario: `{scenario.id}`
- Starting commit: `{commit}`
- Workspace: the currently opened isolated Git worktree only
- Label: {scenario.label}, not a prediction

## Requirement

{scenario.requirement.strip()}

## Public acceptance criteria

{criteria}

## Public interface

{endpoints}

### Rules

{rules}

## Execution contract

- Editable paths: {paths}
- Do not modify `pyproject.toml`, Git metadata, task metadata, or anything outside this workspace.
- Do not access parent directories, other worktrees, the FutureFork repository, external data, or the network.
- Allowed commands: {commands}
- Limits: {scenario.limits.wall_seconds} wall-clock seconds, at most {scenario.limits.max_attempts} implementation attempts, at most {scenario.limits.max_output_bytes} output bytes.

Implement the smallest coherent solution. Preserve all current behavior. Stop when the public
tests pass or the attempt limit is reached. In the final response, report assumptions, changed
files, tests run, and any unresolved issue. Do not claim external acceptance results.
"""


# --- shared plumbing --------------------------------------------------------------------------------------------

def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _artifact(path: Path, run_dir: Path, kind: mf.ArtifactKind) -> mf.Artifact:
    data = path.read_bytes()
    return mf.Artifact(path=path.relative_to(run_dir).as_posix(), kind=kind,
                       sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data))


def _toolchain(config: RunnerConfig) -> dict[str, str]:
    values = {"python": platform.python_version()}
    try:
        out = subprocess.run([config.git_executable, "--version"], capture_output=True, text=True, timeout=10)
        if out.returncode == 0:
            values["git"] = out.stdout.strip().removeprefix("git version ").strip()[:200]
    except Exception:
        pass
    return values


def _boundary_events(changed: list[dict], editable_paths: list[str], evidence_path: str) -> list[mf.Event]:
    events = []
    for entry in changed:
        path = entry["path"]
        if not any(fnmatch.fnmatch(path, pattern) for pattern in editable_paths):
            events.append(mf.Event(
                description=f"changed path {path!r} (status {entry['status']}) is outside the scenario's editable_paths",
                provenance="observed", evidence=evidence_path,
            ))
    return events


def _sentinel_hash(exc: Exception) -> str:
    """A syntactically valid, deterministic-but-clearly-not-the-real-pack hash, used only when the
    mount is damaged badly enough (e.g. a symlink) that we cannot hash it normally at all."""
    return hashlib.sha256(f"TAMPER-UNREADABLE:{exc}".encode()).hexdigest()


def _parse_name_status(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        out.append({"status": parts[0], "path": parts[-1]})
    return sorted(out, key=lambda e: e["path"])


def _parse_numstat(text: str) -> tuple[int, int]:
    added = deleted = 0
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        added += int(parts[0]) if parts[0].isdigit() else 0
        deleted += int(parts[1]) if parts[1].isdigit() else 0
    return added, deleted


# --- prepare -----------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class PrepareResult:
    run_id: str
    run_dir: Path
    worktree_path: Path | None
    outcome: mf.Outcome | None    # None: awaiting Bob (call finalize later); otherwise already terminal
    task_packet_path: Path | None


def prepare(config: RunnerConfig, candidate_ref: str, scenario_path: Path | str, *,
            run_id: str | None = None, now: datetime | None = None) -> PrepareResult:
    if not _NAME_RE.fullmatch(candidate_ref):
        raise InvalidNameError(f"candidate ref must match {SCENARIO_ID_PATTERN!r}: {candidate_ref!r}")
    scenario_path = Path(scenario_path)
    scenario = load_scenario(scenario_path)
    frozen = testpack.load_frozen(_packs_json(config)).get(scenario.id)
    if frozen is None:
        raise RunnerError(f"no frozen protected pack recorded for scenario {scenario.id!r} in {_packs_json(config)}")
    pack_sha256 = frozen["pack_sha256"]

    if run_id is not None:
        run_dir = _run_dir(config, run_id)   # validates the run_id's shape first
        expected_suffix = f"-{candidate_ref}-{load_scenario(scenario_path).id}"
        if not run_id.endswith(expected_suffix):
            raise InvalidNameError(f"run_id must end with {expected_suffix!r}: {run_id!r}")
        started_at = datetime.strptime(run_id.split("-", 1)[0], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    else:
        started_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
        run_id = generate_run_id(candidate_ref, scenario.id, started_at)
        run_dir = _run_dir(config, run_id)
    config.runs_root.mkdir(parents=True, exist_ok=True)
    try:
        run_dir.mkdir(parents=False, exist_ok=False)
    except FileExistsError as exc:
        raise RunCollisionError(f"run directory already exists: {run_dir}") from exc

    _write(run_dir / "scenario.yaml", scenario_path.read_text(encoding="utf-8"))
    scenario_sha = scenario_sha256(scenario_path)
    task_packet_path = run_dir / "task-packet.md"
    mgr = _worktree_manager(config)

    try:
        wt = mgr.create(run_id, candidate_ref)
    except WorktreeError as exc:
        outcome = mf.Outcome(exc.manifest_outcome)
        _write(task_packet_path, "(candidate could not be resolved; no task packet was generated)\n")
        commit = "0" * 40
        try:
            _, commit, _ = mgr.resolve(candidate_ref)
        except Exception:
            pass
        _write_pre_agent_manifest(config, run_dir, run_id, started_at, candidate_ref, commit, scenario, scenario_sha,
                                  pack_sha256, outcome, str(exc), extra_logs=None)
        return PrepareResult(run_id, run_dir, None, outcome, None)

    _write(task_packet_path, render_task_packet(scenario, candidate_ref, wt.commit))

    if scenario.setup_command:
        if not _in_allowlist(scenario.setup_command, scenario.command_allowlist):
            wt.retain("setup_command is not in the scenario's command_allowlist; preserved for inspection")
            _write_state(run_dir, run_id, config, candidate_ref, scenario, scenario_path, scenario_sha, wt, started_at, pack_sha256)
            _write_pre_agent_manifest(config, run_dir, run_id, started_at, candidate_ref, wt.commit, scenario, scenario_sha,
                                      pack_sha256, mf.Outcome.SETUP_FAILED, "setup_command is outside command_allowlist", None)
            return PrepareResult(run_id, run_dir, wt.path, mf.Outcome.SETUP_FAILED, task_packet_path)
        result = run_limited_command(scenario.setup_command, cwd=wt.path, timeout=scenario.limits.wall_seconds,
                                     max_output_bytes=scenario.limits.max_output_bytes)
        _write(run_dir / "stdout.log", f"$ {' '.join(scenario.setup_command)}\n{result.stdout}")
        _write(run_dir / "stderr.log", result.stderr)
        if result.timed_out or result.returncode != 0:
            wt.retain("setup_command failed; preserved for inspection (use `futurefork cleanup` to remove it)")
            detail = "setup_command timed out" if result.timed_out else f"setup_command exited {result.returncode}"
            _write_state(run_dir, run_id, config, candidate_ref, scenario, scenario_path, scenario_sha, wt, started_at, pack_sha256)
            _write_pre_agent_manifest(config, run_dir, run_id, started_at, candidate_ref, wt.commit, scenario, scenario_sha,
                                      pack_sha256, mf.Outcome.SETUP_FAILED, detail, extra_logs=("stdout.log", "stderr.log"))
            return PrepareResult(run_id, run_dir, wt.path, mf.Outcome.SETUP_FAILED, task_packet_path)

    _write_state(run_dir, run_id, config, candidate_ref, scenario, scenario_path, scenario_sha, wt, started_at, pack_sha256)
    return PrepareResult(run_id, run_dir, wt.path, None, task_packet_path)


def _write_state(run_dir, run_id, config, candidate_ref, scenario, scenario_path, scenario_sha, wt: Worktree,
                 started_at, pack_sha256) -> None:
    state = {
        "run_id": run_id, "started_at": started_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": str(config.repo), "worktree_root": str(config.worktree_root),
        "candidate": {"name": candidate_ref, "ref": candidate_ref, "starting_commit": wt.commit},
        "scenario": {"id": scenario.id, "path": str(scenario_path), "sha256": scenario_sha},
        "worktree": {
            "path": str(wt.path), "ref": wt.ref, "full_ref": wt.full_ref, "commit": wt.commit, "tree": wt.tree,
            "source_dirty": wt.source_dirty, "dirty_source_paths": list(wt.dirty_source_paths),
            "watch_refs": wt.watch_refs,
        },
        "evaluator": {"test_pack_sha256": pack_sha256},
    }
    (run_dir / STATE_FILE).write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_pre_agent_manifest(config, run_dir, run_id, started_at, candidate_name, commit, scenario, scenario_sha,
                              pack_sha256, outcome: mf.Outcome, detail: str, extra_logs) -> None:
    """candidate_invalid / setup_failed: no agent work ever happened (manifest's _NO_AGENT_YET)."""
    artifacts = [_artifact(run_dir / "scenario.yaml", run_dir, mf.ArtifactKind.SCENARIO)]
    if (run_dir / "task-packet.md").exists():
        artifacts.append(_artifact(run_dir / "task-packet.md", run_dir, mf.ArtifactKind.TASK_PACKET))
    if (run_dir / STATE_FILE).exists():
        artifacts.append(_artifact(run_dir / STATE_FILE, run_dir, mf.ArtifactKind.OTHER))
    for name, kind in (("stdout.log", mf.ArtifactKind.STDOUT_LOG), ("stderr.log", mf.ArtifactKind.STDERR_LOG)):
        if extra_logs and name in extra_logs and (run_dir / name).exists():
            artifacts.append(_artifact(run_dir / name, run_dir, kind))

    finished_at = datetime.now(timezone.utc).replace(microsecond=0)
    run_manifest = mf.RunManifest(
        schema_version=1, run_id=run_id,
        candidate=mf.Candidate(name=candidate_name, ref=candidate_name, starting_commit=commit),
        scenario=mf.ScenarioRef(id=scenario.id, sha256=scenario_sha),
        evaluator=mf.Evaluator(test_pack_sha256=pack_sha256),
        agent=mf.Agent(provider="IBM Bob", task_id=None, human_triggered=True),
        limits=scenario.limits, toolchain=_toolchain(config),
        started_at=started_at, finished_at=finished_at, outcome=outcome, outcome_detail=detail[:2000],
        tests=mf.Tests(regression=mf.TestRun(state=mf.TestState.NOT_RUN), protected=mf.TestRun(state=mf.TestState.NOT_RUN)),
        measurements=mf.Measurements(attempts=0), artifacts=artifacts,
    )
    mf.write_manifest(run_manifest, run_dir / MANIFEST_FILE)


# --- finalize ------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class FinalizeResult:
    run_id: str
    outcome: mf.Outcome
    manifest_path: Path
    cleanup_error: str | None


def _load_state(run_dir: Path) -> dict:
    path = run_dir / STATE_FILE
    if not path.exists():
        raise RunNotFoundError(f"no {STATE_FILE} in {run_dir}: this run was never prepared (or is already terminal)")
    return json.loads(path.read_text(encoding="utf-8"))


def _reconstruct_worktree(run_id: str, state: dict, git_executable: str = "git") -> tuple[WorktreeManager, Worktree]:
    mgr = WorktreeManager(state["repo"], state["worktree_root"], git_executable=git_executable)
    w = state["worktree"]
    wt = Worktree(run_id=run_id, path=Path(w["path"]), repo=Path(state["repo"]), ref=w["ref"], full_ref=w["full_ref"],
                 commit=w["commit"], tree=w["tree"], source_dirty=w["source_dirty"],
                 dirty_source_paths=tuple(w["dirty_source_paths"]), watch_refs=w["watch_refs"])
    return mgr, wt


def finalize(config: RunnerConfig, run_id: str, *, task_id: str, human_triggered: bool = True,
            attempts: int = 1) -> FinalizeResult:
    run_dir = _run_dir(config, run_id)
    if (run_dir / MANIFEST_FILE).exists():
        raise RunAlreadyFinalizedError(f"run {run_id} is already finalized: {run_dir / MANIFEST_FILE}")
    state = _load_state(run_dir)
    scenario = load_scenario(state["scenario"]["path"])
    started_at = datetime.strptime(state["started_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    mgr, wt = _reconstruct_worktree(run_id, state, config.git_executable)

    registered_paths = {os.path.realpath(e["realpath"]) for e in mgr.registered()}
    if not wt.path.is_dir() or os.path.realpath(wt.path) not in registered_paths:
        return _write_early_runner_error(config, mgr, None, run_dir, run_id, started_at, state, scenario,
                                         task_id, human_triggered,
                                         "the prepared worktree no longer exists or is not registered")
    try:
        mgr.verify_sources(wt)
    except WorktreeError as exc:
        return _write_early_runner_error(config, mgr, wt, run_dir, run_id, started_at, state, scenario,
                                         task_id, human_triggered,
                                         f"source refs changed between prepare and finalize: {exc}")

    events: list[dict] = []

    def note(message: str) -> None:
        events.append({"seq": len(events) + 1, "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                      "message": message})

    note(f"finalize started for candidate={state['candidate']['name']} scenario={scenario.id} task_id={task_id}")

    # A previous finalize attempt can fail after mounting the protected pack but
    # before cleanup.  Remove only an exact, verified leftover *before* staging
    # the agent patch; otherwise `git add -A` would leak evaluator files into
    # patch.diff and changed-paths.json on resume.
    pack_source = _pack_source(config, scenario)
    frozen_files = testpack.load_frozen(_packs_json(config))[scenario.id]["files"]
    mount_dest = wt.path / scenario.protected_tests.mount
    if os.path.lexists(mount_dest):
        try:
            testpack.verify(mount_dest, frozen_files)
        except (testpack.PackMismatch, ValueError) as exc:
            return _write_early_runner_error(
                config, mgr, wt, run_dir, run_id, started_at, state, scenario,
                task_id, human_triggered,
                f"leftover protected mount did not match the frozen pack before patch capture: {exc}",
                boundary_events=[mf.Event(
                    description=(
                        f"mount destination {scenario.protected_tests.mount!r} "
                        "pre-existed and did not match the frozen pack"
                    ),
                    provenance="observed",
                )],
            )
        note(
            f"resuming: removing a verified leftover mount at "
            f"{scenario.protected_tests.mount!r} before patch capture"
        )
        shutil.rmtree(mount_dest)

    # 1. Freeze the patch and changed paths *before* mounting anything or running any test.
    mgr._git(["add", "-A"], cwd=wt.path)  # same package; WorktreeManager has no public "stage everything" op
    tree = mgr._git(["write-tree"], cwd=wt.path).stdout.strip()
    diff_text = mgr._git(["diff", "--cached", wt.commit], cwd=wt.path).stdout
    changed = _parse_name_status(mgr._git(["diff", "--cached", "--name-status", wt.commit], cwd=wt.path).stdout)
    lines_added, lines_deleted = _parse_numstat(mgr._git(["diff", "--cached", "--numstat", wt.commit], cwd=wt.path).stdout)
    (run_dir / "patch.diff").write_text(diff_text, encoding="utf-8")
    (run_dir / "changed-paths.json").write_text(json.dumps(changed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    note(f"patch frozen: {len(changed)} changed path(s), tree {tree}")

    boundary_events = _boundary_events(changed, scenario.editable_paths, "changed-paths.json")
    for event in boundary_events:
        note(f"boundary observation: {event.description}")

    common = dict(config=config, mgr=mgr, wt=wt, run_dir=run_dir, run_id=run_id, started_at=started_at, state=state,
                 scenario=scenario, task_id=task_id, human_triggered=human_triggered, changed=changed,
                 lines_added=lines_added, lines_deleted=lines_deleted, tree=tree, events=events)

    # 2. Verify + mount the protected pack, now that editing is frozen.
    try:
        testpack.mount_pack(pack_source, mount_dest, frozen_files)
    except testpack.PackMismatch as exc:
        note(f"protected pack SOURCE failed verification before mount: {exc}")
        return _write_post_agent_manifest(**common, outcome=mf.Outcome.RUNNER_ERROR,
                                          detail=f"protected pack source does not match PACKS.json: {exc}",
                                          reg=mf.TestRun(state=mf.TestState.NOT_RUN),
                                          prot=mf.TestRun(state=mf.TestState.NOT_RUN),
                                          attempts=0, duration=0.0, output_bytes=0,
                                          boundary_events=boundary_events, observed_pack_hash=None)
    note(f"protected pack mounted and verified at {scenario.protected_tests.mount}")

    # 3. Run regression, then (if it passed) protected tests.
    stdout_log, stderr_log = [], []
    total_duration = 0.0
    total_output = 0

    def run_phase(command: list[str]) -> CommandResult:
        nonlocal total_duration, total_output
        r = run_limited_command(command, cwd=wt.path, timeout=scenario.limits.wall_seconds,
                                max_output_bytes=scenario.limits.max_output_bytes)
        stdout_log.append(f"$ {' '.join(command)}\n{r.stdout}\n")
        stderr_log.append(r.stderr)
        total_duration += r.duration_seconds
        total_output += r.total_bytes
        return r

    reg_result = run_phase(scenario.dev_test_command)
    reg_state, reg_counts = classify_test_run(reg_result)
    reg = _test_run(reg_state, list(scenario.dev_test_command), reg_result, reg_counts, "test-results.json")
    note(f"regression: state={reg_state.value} returncode={reg_result.returncode} timed_out={reg_result.timed_out}")

    prot = mf.TestRun(state=mf.TestState.NOT_RUN)
    prot_result: CommandResult | None = None
    prot_counts: dict | None = None
    if reg_state is mf.TestState.PASSED:
        prot_result = run_phase(scenario.protected_test_command)
        prot_state, prot_counts = classify_test_run(prot_result)
        prot = _test_run(prot_state, list(scenario.protected_test_command), prot_result, prot_counts, "test-results.json")
        note(f"protected: state={prot_state.value} returncode={prot_result.returncode} timed_out={prot_result.timed_out}")
    else:
        note("protected tests were not run (regression did not pass)")

    (run_dir / "stdout.log").write_text("".join(stdout_log), encoding="utf-8")
    (run_dir / "stderr.log").write_text("".join(stderr_log), encoding="utf-8")
    (run_dir / "test-results.json").write_text(json.dumps({
        "regression": {"command": list(scenario.dev_test_command),
                       "returncode": None if reg_result.timed_out else reg_result.returncode,
                       "timed_out": reg_result.timed_out, "counts": reg_counts},
        "protected": {"command": list(scenario.protected_test_command),
                     "returncode": None if prot_result is None or prot_result.timed_out else prot_result.returncode,
                     "timed_out": prot_result.timed_out if prot_result else None, "counts": prot_counts},
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # 4. Re-verify the mounted pack, regardless of what the tests showed.
    tampered = False
    try:
        observed_pack_hash = testpack.verify(mount_dest, frozen_files)
    except testpack.PackMismatch as exc:
        tampered = True
        note(f"protected pack TAMPER DETECTED after test execution: {exc}")
        try:
            observed_pack_hash = testpack.pack_sha256(mount_dest)
        except ValueError as walk_exc:
            observed_pack_hash = _sentinel_hash(walk_exc)
    except ValueError as exc:  # a symlink was introduced into the mount
        tampered = True
        observed_pack_hash = _sentinel_hash(exc)
        note(f"protected pack TAMPER DETECTED (symlink) after test execution: {exc}")

    attempts_final = max(attempts, 1)
    if tampered:
        outcome, detail = mf.Outcome.ORACLE_TAMPERED, "the protected pack no longer matches PACKS.json after the test run"
        if prot.state is not mf.TestState.NOT_RUN:
            prot = mf.TestRun(state=mf.TestState.ERROR, command=list(scenario.protected_test_command))
    elif reg_result.timed_out:
        outcome, detail = mf.Outcome.BUDGET_EXHAUSTED, "regression tests exceeded the scenario's wall_seconds limit"
    elif prot_result is not None and prot_result.timed_out:
        outcome, detail = mf.Outcome.BUDGET_EXHAUSTED, "protected tests exceeded the scenario's wall_seconds limit"
    elif reg_state is mf.TestState.ERROR:
        outcome, detail = mf.Outcome.RUNNER_ERROR, "the regression test command produced no trustworthy result"
    elif reg_state is mf.TestState.FAILED:
        outcome, detail = mf.Outcome.REGRESSION_FAILED, None
    elif prot.state is mf.TestState.ERROR:
        outcome, detail = mf.Outcome.RUNNER_ERROR, "the protected test command produced no trustworthy result"
    elif prot.state is mf.TestState.FAILED:
        outcome, detail = mf.Outcome.ACCEPTANCE_FAILED, None
    else:
        outcome, detail = mf.Outcome.COMPLETED, None

    if outcome in (mf.Outcome.REGRESSION_FAILED, mf.Outcome.ACCEPTANCE_FAILED) and attempts_final >= scenario.limits.max_attempts:
        outcome = mf.Outcome.BUDGET_EXHAUSTED
        detail = f"operator-reported attempts ({attempts_final}) reached the scenario's max_attempts limit"

    if attempts != 1:
        boundary_events = [*boundary_events, mf.Event(
            description=f"operator reported {attempts} Bob implementation attempt(s) inside the IDE",
            provenance="reported")]

    return _write_post_agent_manifest(**common, outcome=outcome, detail=detail, reg=reg, prot=prot,
                                      attempts=attempts_final, duration=total_duration, output_bytes=total_output,
                                      boundary_events=boundary_events, observed_pack_hash=observed_pack_hash)


def _write_early_runner_error(config, mgr, wt, run_dir, run_id, started_at, state, scenario, task_id,
                              human_triggered, detail: str,
                              boundary_events: list[mf.Event] | None = None) -> FinalizeResult:
    """Something is wrong before we can even trust the worktree: no patch, no test attempt."""
    return _write_post_agent_manifest(
        config=config, mgr=mgr, wt=wt, run_dir=run_dir, run_id=run_id, started_at=started_at, state=state,
        scenario=scenario, task_id=task_id, human_triggered=human_triggered, changed=[], lines_added=0,
        lines_deleted=0, tree=None, events=[{"seq": 1, "message": detail}], outcome=mf.Outcome.RUNNER_ERROR,
        detail=detail, reg=mf.TestRun(state=mf.TestState.NOT_RUN), prot=mf.TestRun(state=mf.TestState.NOT_RUN),
        attempts=0, duration=0.0, output_bytes=0, boundary_events=boundary_events or [],
        observed_pack_hash=None,
    )


def _write_post_agent_manifest(*, config, mgr, wt, run_dir, run_id, started_at, state, scenario, task_id,
                               human_triggered, changed, lines_added, lines_deleted, tree, events,
                               outcome: mf.Outcome, detail: str | None, reg: mf.TestRun, prot: mf.TestRun,
                               attempts: int, duration: float, output_bytes: int,
                               boundary_events: list[mf.Event], observed_pack_hash: str | None) -> FinalizeResult:
    (run_dir / "events.jsonl").write_text("".join(json.dumps(e, sort_keys=True) + "\n" for e in events), encoding="utf-8")
    measurements = mf.Measurements(
        attempts=attempts, duration_seconds=round(duration, 3), output_bytes=output_bytes,
        changed_files=len(changed), lines_added=lines_added, lines_deleted=lines_deleted,
        boundary_violations=boundary_events,
    )
    (run_dir / "measurements.json").write_text(measurements.model_dump_json(indent=2) + "\n", encoding="utf-8")
    ending = mf.Ending(tree=tree, diff_artifact="patch.diff") if tree is not None else None

    kinds = {
        "scenario.yaml": mf.ArtifactKind.SCENARIO, "task-packet.md": mf.ArtifactKind.TASK_PACKET,
        "patch.diff": mf.ArtifactKind.PATCH, "changed-paths.json": mf.ArtifactKind.CHANGED_PATHS,
        "test-results.json": mf.ArtifactKind.TEST_RESULTS, "measurements.json": mf.ArtifactKind.MEASUREMENTS,
        "events.jsonl": mf.ArtifactKind.EVENTS, "stdout.log": mf.ArtifactKind.STDOUT_LOG,
        "stderr.log": mf.ArtifactKind.STDERR_LOG, STATE_FILE: mf.ArtifactKind.OTHER,
    }
    artifacts = [_artifact(run_dir / name, run_dir, kind) for name, kind in kinds.items() if (run_dir / name).exists()]
    hashes = {a.path: {"sha256": a.sha256, "size_bytes": a.size_bytes} for a in artifacts}
    (run_dir / "artifact-hashes.json").write_text(json.dumps(hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    artifacts.append(_artifact(run_dir / "artifact-hashes.json", run_dir, mf.ArtifactKind.ARTIFACT_HASHES))

    finished_at = datetime.now(timezone.utc).replace(microsecond=0)
    run_manifest = mf.RunManifest(
        schema_version=1, run_id=run_id, candidate=mf.Candidate(**state["candidate"]),
        scenario=mf.ScenarioRef(id=scenario.id, sha256=state["scenario"]["sha256"]),
        evaluator=mf.Evaluator(test_pack_sha256=state["evaluator"]["test_pack_sha256"],
                               observed_sha256_after_run=observed_pack_hash),
        agent=mf.Agent(provider="IBM Bob", task_id=task_id, human_triggered=human_triggered),
        limits=scenario.limits, toolchain=_toolchain(config), started_at=started_at, finished_at=finished_at,
        outcome=outcome, outcome_detail=(detail[:2000] if detail else None),
        tests=mf.Tests(regression=reg, protected=prot), measurements=measurements, ending=ending, artifacts=artifacts,
    )
    mf.write_manifest(run_manifest, run_dir / MANIFEST_FILE)

    cleanup_error = None
    if wt is not None and mgr is not None and not wt.retained:
        try:
            mgr.remove(wt)
        except CleanupError as exc:
            cleanup_error = str(exc)
    return FinalizeResult(run_id, outcome, run_dir / MANIFEST_FILE, cleanup_error)


# --- inspect / cleanup ------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class RunStatus:
    run_id: str
    prepared: bool
    finalized: bool
    outcome: mf.Outcome | None
    worktree_path: Path | None


def inspect(config: RunnerConfig, run_id: str) -> RunStatus:
    run_dir = _run_dir(config, run_id)
    if not run_dir.is_dir():
        raise RunNotFoundError(f"no such run: {run_dir}")
    manifest_path = run_dir / MANIFEST_FILE
    if manifest_path.exists():
        m = mf.load_manifest(manifest_path)
        return RunStatus(run_id, True, True, m.outcome, None)
    state_path = run_dir / STATE_FILE
    if not state_path.exists():
        return RunStatus(run_id, False, False, None, None)
    state = json.loads(state_path.read_text())
    return RunStatus(run_id, True, False, None, Path(state["worktree"]["path"]))


def cleanup(config: RunnerConfig, run_id: str) -> None:
    """Remove a retained (e.g. setup_failed) worktree for `run_id` via WorktreeManager.remove."""
    run_dir = _run_dir(config, run_id)
    state = _load_state(run_dir)
    mgr, wt = _reconstruct_worktree(run_id, state, config.git_executable)
    mgr.remove(wt)
