"""P0.6+P0.7: the operator-driven runner CLI. Every test uses temporary repositories, packs, and
run/worktree roots only. An autouse guard proves the real repo, its refs, and the P0.3 worktree
are byte-identical before and after this whole module (same discipline as tests/test_worktrees.py)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import textwrap
import time
from pathlib import Path

import pytest

from futurefork import manifest as mf
from futurefork import runner
from futurefork import testpack

ROOT = Path(__file__).resolve().parents[1]
P03 = Path("/private/tmp/futurefork-p03-modular")
GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "FutureFork Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "FutureFork Test", "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
}
# The scenario commands say "python"; make sure that resolves to this venv's interpreter no
# matter what the ambient shell's PATH looks like.
PY_BIN_DIR = str(Path(os.environ.get("VIRTUAL_ENV", ROOT / ".venv")) / "bin")
RUN_ENV = {**os.environ, "PATH": PY_BIN_DIR + os.pathsep + os.environ.get("PATH", "")}


# --- production-repo guard (same pattern as test_worktrees.py) -----------------------------------------------

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
    state = {"refs": git("for-each-ref", "--format=%(refname) %(objectname)"), "head": git("rev-parse", "HEAD"),
            "worktrees": git("worktree", "list", "--porcelain"),
            "status": git("status", "--porcelain", "--untracked-files=all"), "content": _content_hash(ROOT)}
    if P03.exists():
        state["p03_content"] = _content_hash(P03)
        state["p03_status"] = subprocess.run(["git", "-C", str(P03), "status", "--porcelain", "--untracked-files=all"],
                                             capture_output=True, text=True, env=env).stdout
    return state


@pytest.fixture(scope="module", autouse=True)
def real_repository_is_untouched():
    before = _real_state()
    assert "coupled" in before["refs"] and "modular" in before["refs"]
    yield
    after = _real_state()
    assert after == before, {k: (before[k], after[k]) for k in before if before[k] != after[k]}


# --- building a throwaway repo (candidate branch + orchestrator-side scenario/pack) ------------------------------

def git(repo: Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, env=GIT_ENV)
    if check and r.returncode:
        raise AssertionError(f"git {args} failed: {r.stderr}")
    return r.stdout.strip()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


SCENARIO_TEMPLATE = """\
schema_version: 1
id: {id}
title: Sample
label: hypothesis
requirement: "Do the thing."
public_acceptance_criteria: ["it works"]
public_interface:
  endpoints:
    - method: POST
      path: /x
      summary: does a thing
  rules: ["rule one"]
setup_command: {setup_command}
dev_test_command: [python, -m, pytest, -q, tests]
protected_test_command: [python, -m, pytest, -q, .futurefork-evaluator/{id}]
protected_tests:
  source: scenarios/demo/protected-tests/{id}
  mount: .futurefork-evaluator/{id}
editable_paths: {editable_paths}
protected_paths: [".futurefork-evaluator/**"]
command_allowlist: [[python, -m, pytest]]
limits: {{wall_seconds: {wall_seconds}, max_attempts: {max_attempts}, max_output_bytes: {max_output_bytes}}}
tags: [x]
"""


def build_repo(tmp_path: Path, *, scenario_id: str = "sample", wall_seconds: int = 30, max_attempts: int = 4,
              max_output_bytes: int = 1_000_000, setup_command: list[str] | None = None,
              editable_paths: list[str] | None = None) -> Path:
    """A temp repo with a `main` (orchestrator: scenario + frozen pack) and a `modular` candidate
    branch (src/tests only — no scenarios/ in its tree, matching the real product's contamination rule)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    write(repo / "pyproject.toml", '[tool.pytest.ini_options]\npythonpath = ["src"]\n')
    write(repo / "src" / "pkg" / "__init__.py", "X = 1\n")
    write(repo / "tests" / "test_x.py", "def test_x():\n    assert True\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    git(repo, "branch", "modular", "main")   # candidate branch: identical tree, no scenarios/ ever added to it

    write(repo / "scenarios" / "demo" / "protected-tests" / scenario_id / f"test_{scenario_id}.py", textwrap.dedent("""\
        def test_guard():
            from pkg import X
            assert X == 1

        def test_future():
            from pkg import Y
            assert Y == 2
    """))
    manifest = testpack.build_manifest(repo / "scenarios" / "demo" / "protected-tests")
    write(repo / "scenarios" / "demo" / "protected-tests" / "PACKS.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    write(repo / "scenario.yaml", SCENARIO_TEMPLATE.format(
        id=scenario_id, setup_command=json.dumps(setup_command or []),
        editable_paths=json.dumps(editable_paths or ["src/**", "tests/**"]),
        wall_seconds=wall_seconds, max_attempts=max_attempts, max_output_bytes=max_output_bytes,
    ))
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "orchestrator: scenario + frozen pack")
    return repo


def make_config(tmp_path: Path, repo: Path) -> runner.RunnerConfig:
    return runner.RunnerConfig(repo=repo, runs_root=tmp_path / "runs", worktree_root=tmp_path / "worktrees")


@pytest.fixture
def repo(tmp_path) -> Path:
    return build_repo(tmp_path)


@pytest.fixture
def config(tmp_path, repo) -> runner.RunnerConfig:
    return make_config(tmp_path, repo)


def edit_worktree(worktree: Path, extra_lines: str = "Y = 2\n") -> None:
    with open(worktree / "src" / "pkg" / "__init__.py", "a") as f:
        f.write(extra_lines)


@pytest.fixture(autouse=True)
def _use_venv_path(monkeypatch):
    monkeypatch.setenv("PATH", RUN_ENV["PATH"])


# --- prepare: hides the oracle, produces valid artifacts, source refs unchanged ------------------------------------

def test_prepare_creates_a_detached_worktree_with_no_oracle_material(config, tmp_path):
    before = git(config.repo, "for-each-ref", "--format=%(refname) %(objectname)")
    result = runner.prepare(config, "modular", config.repo / "scenario.yaml", run_id="20260927T090000Z-modular-sample")
    assert result.outcome is None and result.worktree_path.is_dir()
    assert git(result.worktree_path, "rev-parse", "HEAD") == git(config.repo, "rev-parse", "modular")
    assert subprocess.run(["git", "-C", str(result.worktree_path), "symbolic-ref", "-q", "HEAD"],
                          capture_output=True).returncode == 1  # detached
    for path in result.worktree_path.rglob("*"):
        assert ".futurefork-evaluator" not in path.parts
        assert "protected-tests" not in str(path)
        assert path.name != "PACKS.json"
    assert set(os.listdir(result.worktree_path)) == {".git", "pyproject.toml", "src", "tests"}
    assert git(config.repo, "for-each-ref", "--format=%(refname) %(objectname)") == before


def test_prepare_writes_a_valid_task_packet_and_state(config):
    result = runner.prepare(config, "modular", config.repo / "scenario.yaml", run_id="20260927T090000Z-modular-sample")
    packet = result.task_packet_path.read_text()
    assert "partial" not in packet.lower()  # sanity: not leaking unrelated content
    assert "Do the thing." in packet and "modular" in packet and "editable_paths" not in packet  # rendered, not literal
    state = json.loads((result.run_dir / runner.STATE_FILE).read_text())
    assert state["candidate"]["ref"] == "modular" and state["scenario"]["id"] == "sample"
    assert re.fullmatch(r"[0-9a-f]{40}", state["candidate"]["starting_commit"])
    assert (result.run_dir / "scenario.yaml").read_text() == (config.repo / "scenario.yaml").read_text()


def test_prepare_retains_the_worktree_for_the_operator_and_it_stays_after_the_process_exits(config):
    result = runner.prepare(config, "modular", config.repo / "scenario.yaml", run_id="20260927T090000Z-modular-sample")
    assert result.worktree_path.is_dir()  # not removed: prepare() returned, nothing cleaned it up


# --- render_task_packet: full public interface fidelity (regression for a missing request/response bug) -------------

REAL_SCENARIO_IDS = ["partial-refund", "organization-pricing", "ordered-discounts"]


def _real_scenario(scenario_id: str):
    from futurefork.scenario import load_scenario
    return load_scenario(ROOT / "scenarios" / "demo" / f"{scenario_id}.yaml")


def _errors_block(endpoint) -> str:
    return runner._json_block({str(k): v for k, v in sorted(endpoint.errors.items())})


def test_task_packet_includes_the_exact_public_request_and_response_for_partial_refund():
    scenario = _real_scenario("partial-refund")
    packet = runner.render_task_packet(scenario, "coupled", "f" * 40)
    endpoint = scenario.public_interface.endpoints[0]
    assert endpoint.request and endpoint.response and endpoint.errors  # sanity: the fixture actually has all three
    assert runner._json_block(endpoint.request) in packet
    assert runner._json_block(endpoint.response) in packet
    assert _errors_block(endpoint) in packet
    # the exact field names Bob needs, not just a prose paraphrase
    assert '"items": "[{sku: string, quantity: integer >= 1}]"' in packet
    assert "remaining_refundable_cents" in packet


@pytest.mark.parametrize("scenario_id", REAL_SCENARIO_IDS)
def test_task_packet_represents_every_public_field_of_every_endpoint(scenario_id):
    scenario = _real_scenario(scenario_id)
    packet = runner.render_task_packet(scenario, "coupled", "f" * 40)
    for endpoint in scenario.public_interface.endpoints:
        assert f"`{endpoint.method} {endpoint.path}`" in packet
        assert endpoint.summary in packet
        if endpoint.request:
            assert runner._json_block(endpoint.request) in packet
        if endpoint.response:
            assert runner._json_block(endpoint.response) in packet
        if endpoint.errors:
            assert _errors_block(endpoint) in packet
    for rule in scenario.public_interface.rules:
        assert rule in packet
    for criterion in scenario.public_acceptance_criteria:
        assert criterion in packet


def test_task_packet_rendering_is_deterministic_across_calls_and_key_order():
    from futurefork.scenario import Scenario

    scenario = _real_scenario("partial-refund")
    a = runner.render_task_packet(scenario, "coupled", "a" * 40)
    b = runner.render_task_packet(scenario, "coupled", "a" * 40)
    assert a == b

    data = scenario.model_dump(mode="json")
    endpoint = data["public_interface"]["endpoints"][0]
    endpoint["response"] = {k: endpoint["response"][k] for k in reversed(list(endpoint["response"]))}
    reordered = Scenario.model_validate(data)
    assert runner.render_task_packet(reordered, "coupled", "a" * 40) == a


@pytest.mark.parametrize("scenario_id", REAL_SCENARIO_IDS)
def test_task_packet_never_contains_protected_or_oracle_material(scenario_id):
    scenario = _real_scenario(scenario_id)
    packet = runner.render_task_packet(scenario, "coupled", "f" * 40)
    lowered = packet.lower()
    for banned in ("protected", "oracle", "futurefork-evaluator", "packs.json", "evaluator",
                  scenario.protected_tests.source.lower(), scenario.protected_tests.mount.lower()):
        assert banned not in lowered, banned
    assert str(scenario.protected_test_command) not in packet


def test_packets_for_two_candidates_are_byte_equivalent_after_normalizing_only_candidate_metadata():
    scenario = _real_scenario("partial-refund")
    a = runner.render_task_packet(scenario, "coupled", "a" * 40)
    b = runner.render_task_packet(scenario, "modular", "b" * 40)
    normalize = lambda text, name, commit: text.replace(name, "CANDIDATE").replace(commit, "COMMIT")
    assert normalize(a, "coupled", "a" * 40) == normalize(b, "modular", "b" * 40)


# --- finalize happy path: complete bundle, hashes match bytes, manifest round-trips, immutable ---------------------

def _prepare_and_edit(config, run_id="20260927T090000Z-modular-sample", editor=edit_worktree) -> runner.PrepareResult:
    result = runner.prepare(config, "modular", config.repo / "scenario.yaml", run_id=run_id)
    editor(result.worktree_path)
    return result


def test_finalize_happy_path_produces_a_complete_verifiable_bundle(config):
    result = _prepare_and_edit(config)
    fin = runner.finalize(config, result.run_id, task_id="task-0001-happy")
    assert fin.outcome is mf.Outcome.COMPLETED and fin.cleanup_error is None
    assert not result.worktree_path.exists()  # cleaned up via WorktreeManager

    m = mf.load_manifest(fin.manifest_path)
    assert m.outcome is mf.Outcome.COMPLETED
    expected_files = {"scenario.yaml", "task-packet.md", "patch.diff", "changed-paths.json", "test-results.json",
                      "measurements.json", "events.jsonl", "stdout.log", "stderr.log", "artifact-hashes.json",
                      "state.json"}
    assert expected_files <= {a.path for a in m.artifacts}
    for artifact in m.artifacts:
        data = (result.run_dir / artifact.path).read_bytes()
        assert hashlib.sha256(data).hexdigest() == artifact.sha256, artifact.path
        assert len(data) == artifact.size_bytes, artifact.path
    hashes = json.loads((result.run_dir / "artifact-hashes.json").read_text())
    for a in m.artifacts:
        if a.path != "artifact-hashes.json":
            assert hashes[a.path] == {"sha256": a.sha256, "size_bytes": a.size_bytes}
    assert "artifact-hashes.json" not in hashes  # it never lists itself


def test_finalize_manifest_round_trips_and_is_schema_valid(config):
    result = _prepare_and_edit(config)
    fin = runner.finalize(config, result.run_id, task_id="task-0001-happy")
    text = fin.manifest_path.read_text()
    again = mf.loads_manifest(text)
    assert mf.dump_manifest(again) == text
    assert re.match(mf.RUN_ID_PATTERN, again.run_id)


def test_finalized_run_directory_cannot_be_overwritten(config):
    result = _prepare_and_edit(config)
    runner.finalize(config, result.run_id, task_id="task-0001")
    with pytest.raises(runner.RunAlreadyFinalizedError):
        runner.finalize(config, result.run_id, task_id="task-0002-should-not-apply")
    m = mf.load_manifest(result.run_dir / runner.MANIFEST_FILE)
    assert m.agent.task_id == "task-0001"  # untouched by the second call


def test_patch_and_tree_correctness(config):
    result = _prepare_and_edit(config, editor=lambda wt: edit_worktree(wt, "Y = 2\n") or write(wt / "tests" / "test_new.py", "def test_new():\n    assert True\n"))
    fin = runner.finalize(config, result.run_id, task_id="task-0001")
    m = mf.load_manifest(fin.manifest_path)
    patch = (result.run_dir / "patch.diff").read_text()
    assert "+Y = 2" in patch and "test_new.py" in patch
    changed = json.loads((result.run_dir / "changed-paths.json").read_text())
    assert {"path": "src/pkg/__init__.py", "status": "M"} in changed
    assert any(c["path"] == "tests/test_new.py" and c["status"] == "A" for c in changed)
    assert m.ending.tree is not None and m.ending.tree != m.candidate.starting_commit
    assert re.fullmatch(r"[0-9a-f]{40}", m.ending.tree)
    assert m.measurements.changed_files == 2 and m.measurements.lines_added >= 2


# --- regression_failed, acceptance_failed --------------------------------------------------------------------------

def test_regression_failed_stops_before_protected_tests(config):
    result = _prepare_and_edit(config, editor=lambda wt: write(wt / "tests" / "test_x.py", "def test_x():\n    assert False\n"))
    fin = runner.finalize(config, result.run_id, task_id="task-reg-fail")
    m = mf.load_manifest(fin.manifest_path)
    assert m.outcome is mf.Outcome.REGRESSION_FAILED
    assert m.tests.regression.state is mf.TestState.FAILED and m.tests.protected.state is mf.TestState.NOT_RUN
    assert m.tests.regression.failed == 1


def test_acceptance_failed_when_regression_passes_but_protected_does_not(config):
    result = _prepare_and_edit(config, editor=lambda wt: None)  # no edit: Y is never added
    fin = runner.finalize(config, result.run_id, task_id="task-acc-fail")
    m = mf.load_manifest(fin.manifest_path)
    assert m.outcome is mf.Outcome.ACCEPTANCE_FAILED
    assert m.tests.regression.state is mf.TestState.PASSED and m.tests.protected.state is mf.TestState.FAILED
    assert m.tests.protected.failed == 1 and m.tests.protected.passed == 1  # test_guard passes, test_future fails


# --- candidate_invalid / setup_failed ------------------------------------------------------------------------------

def test_candidate_invalid_for_an_unresolvable_ref(config):
    result = runner.prepare(config, "nosuchbranch", config.repo / "scenario.yaml", run_id="20260927T090000Z-nosuchbranch-sample")
    assert result.outcome is mf.Outcome.CANDIDATE_INVALID and result.worktree_path is None
    m = mf.load_manifest(result.run_dir / runner.MANIFEST_FILE)
    assert m.outcome is mf.Outcome.CANDIDATE_INVALID and m.agent.task_id is None
    assert m.tests.regression.state is mf.TestState.NOT_RUN and m.measurements.attempts == 0
    assert m.candidate.starting_commit == "0" * 40


def test_setup_failed_when_the_setup_command_exits_nonzero(tmp_path):
    # Must start with an allowlisted prefix ([python, -m, pytest]) to reach actual execution
    # rather than being rejected up front for being outside command_allowlist (tested separately).
    repo = build_repo(tmp_path, setup_command=["python", "-m", "pytest", "--this-flag-does-not-exist"])
    config = make_config(tmp_path, repo)
    result = runner.prepare(config, "modular", repo / "scenario.yaml", run_id="20260927T090000Z-modular-sample")
    assert result.outcome is mf.Outcome.SETUP_FAILED
    assert result.worktree_path.is_dir()  # retained for inspection
    m = mf.load_manifest(result.run_dir / runner.MANIFEST_FILE)
    assert m.outcome is mf.Outcome.SETUP_FAILED and "setup_command exited" in m.outcome_detail
    assert m.agent.task_id is None and m.measurements.attempts == 0
    stdout = (result.run_dir / "stdout.log").read_text()
    assert "python -m pytest --this-flag-does-not-exist" in stdout
    runner.cleanup(config, result.run_id)
    assert not result.worktree_path.exists()


def test_setup_failed_when_the_setup_command_is_outside_the_allowlist(tmp_path):
    repo = build_repo(tmp_path, setup_command=["curl", "https://example.invalid"])
    config = make_config(tmp_path, repo)
    result = runner.prepare(config, "modular", repo / "scenario.yaml", run_id="20260927T090000Z-modular-sample")
    assert result.outcome is mf.Outcome.SETUP_FAILED
    m = mf.load_manifest(result.run_dir / runner.MANIFEST_FILE)
    assert "command_allowlist" in m.outcome_detail
    runner.cleanup(config, result.run_id)


def test_setup_failed_on_timeout(tmp_path):
    repo = build_repo(tmp_path, setup_command=["python", "-c", "import time; time.sleep(30)"], wall_seconds=1)
    write(repo / "scenario.yaml", (repo / "scenario.yaml").read_text().replace(
        "command_allowlist: [[python, -m, pytest]]", "command_allowlist: [[python, -m, pytest], [python, -c]]"))
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "widen allowlist for the timeout test")
    config = make_config(tmp_path, repo)
    started = time.monotonic()
    result = runner.prepare(config, "modular", repo / "scenario.yaml", run_id="20260927T090000Z-modular-sample")
    assert time.monotonic() - started < 20
    assert result.outcome is mf.Outcome.SETUP_FAILED
    m = mf.load_manifest(result.run_dir / runner.MANIFEST_FILE)
    assert "timed out" in m.outcome_detail
    runner.cleanup(config, result.run_id)


# --- budget_exhausted -----------------------------------------------------------------------------------------------

def test_budget_exhausted_on_regression_timeout(tmp_path):
    repo = build_repo(tmp_path, wall_seconds=1)
    config = make_config(tmp_path, repo)
    result = runner.prepare(config, "modular", repo / "scenario.yaml", run_id="20260927T090000Z-modular-sample")
    write(result.worktree_path / "tests" / "test_slow.py", "import time\ndef test_slow():\n    time.sleep(30)\n")
    started = time.monotonic()
    fin = runner.finalize(config, result.run_id, task_id="task-slow")
    assert time.monotonic() - started < 20   # the sleeping child was actually killed, not waited out
    m = mf.load_manifest(fin.manifest_path)
    assert m.outcome is mf.Outcome.BUDGET_EXHAUSTED
    assert m.tests.regression.state is mf.TestState.ERROR and m.tests.protected.state is mf.TestState.NOT_RUN
    assert m.measurements.duration_seconds >= 1.0


def test_budget_exhausted_when_operator_reports_attempts_at_the_limit(config):
    result = _prepare_and_edit(config, editor=lambda wt: write(wt / "tests" / "test_x.py", "def test_x():\n    assert False\n"))
    fin = runner.finalize(config, result.run_id, task_id="task-budget", attempts=4)  # scenario max_attempts=4
    m = mf.load_manifest(fin.manifest_path)
    assert m.outcome is mf.Outcome.BUDGET_EXHAUSTED
    assert m.measurements.attempts == 4


# --- runner_error: pack source tampered before mount ------------------------------------------------------------------

def test_runner_error_when_the_source_pack_no_longer_matches_packs_json(config):
    pack_file = config.repo / "scenarios" / "demo" / "protected-tests" / "sample" / "test_sample.py"
    pack_file.write_text(pack_file.read_text() + "\n# tampered after freezing\n")
    result = _prepare_and_edit(config)
    fin = runner.finalize(config, result.run_id, task_id="task-src-tamper")
    m = mf.load_manifest(fin.manifest_path)
    assert m.outcome is mf.Outcome.RUNNER_ERROR
    assert "source" in m.outcome_detail.lower()
    assert m.tests.regression.state is mf.TestState.NOT_RUN  # never even attempted
    assert not result.worktree_path.exists()


def test_runner_error_when_a_pre_existing_unrelated_file_occupies_the_mount_path(config):
    result = _prepare_and_edit(config)
    write(result.worktree_path / ".futurefork-evaluator" / "sample" / "unrelated.txt", "not the pack\n")
    fin = runner.finalize(config, result.run_id, task_id="task-occupied")
    m = mf.load_manifest(fin.manifest_path)
    assert m.outcome is mf.Outcome.RUNNER_ERROR
    assert any("pre-existed and did not match" in e.description for e in m.measurements.boundary_violations)


# --- oracle_tampered: mounted tamper during/after the test run ---------------------------------------------------------

def test_oracle_tampered_when_the_candidates_own_tests_modify_the_mounted_pack(config):
    def editor(wt: Path) -> None:
        edit_worktree(wt)  # keep both regression and protected passing on their own merits
        target = ".futurefork-evaluator/sample/test_sample.py"
        write(wt / "tests" / "test_tamper.py", textwrap.dedent(f"""\
            import os

            def test_tamper():
                os.chmod({target!r}, 0o644)
                with open({target!r}, "a") as f:
                    f.write("# tampered by the candidate's own test\\n")
                assert True
        """))

    result = _prepare_and_edit(config, editor=editor)
    fin = runner.finalize(config, result.run_id, task_id="task-tamper")
    m = mf.load_manifest(fin.manifest_path)
    assert m.outcome is mf.Outcome.ORACLE_TAMPERED
    assert m.tests.protected.state is not mf.TestState.PASSED
    assert m.evaluator.observed_sha256_after_run is not None
    assert m.evaluator.observed_sha256_after_run != m.evaluator.test_pack_sha256
    assert not result.worktree_path.exists()  # still cleaned up normally


@pytest.mark.parametrize("tamper", ["add", "remove", "symlink"])
def test_oracle_tampered_for_added_removed_and_symlinked_mount_files(config, tamper):
    ops = {
        "add": 'open(".futurefork-evaluator/sample/extra.py", "w").write("x = 1\\n")',
        "remove": 'import os; os.remove(".futurefork-evaluator/sample/test_sample.py")',
        "symlink": 'import os; os.remove(".futurefork-evaluator/sample/test_sample.py"); os.symlink("/etc/hosts", ".futurefork-evaluator/sample/test_sample.py")',
    }

    def editor(wt: Path) -> None:
        edit_worktree(wt)
        write(wt / "tests" / "test_tamper.py", "def test_tamper():\n    " + ops[tamper].replace("\n", "\n    ") + "\n    assert True\n")

    result = _prepare_and_edit(config, editor=editor)
    fin = runner.finalize(config, result.run_id, task_id=f"task-tamper-{tamper}")
    m = mf.load_manifest(fin.manifest_path)
    assert m.outcome is mf.Outcome.ORACLE_TAMPERED
    assert m.evaluator.observed_sha256_after_run != m.evaluator.test_pack_sha256


# --- test-command parsing --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("stdout,expected", [
    ("...\n47 passed in 0.07s\n", {"passed": 47, "failed": 0, "errors": 0, "skipped": 0}),
    ("...\n2 failed, 45 passed in 0.10s\n", {"passed": 45, "failed": 2, "errors": 0, "skipped": 0}),
    ("...\n1 error in 0.05s\n", {"passed": 0, "failed": 0, "errors": 1, "skipped": 0}),
    ("...\n3 passed, 1 skipped in 0.01s\n", {"passed": 3, "failed": 0, "errors": 0, "skipped": 1}),
    ("no recognizable summary here", None),
    ("", None),
])
def test_parse_pytest_summary(stdout, expected):
    assert runner.parse_pytest_summary(stdout) == expected


def _result(returncode, stdout, timed_out=False):
    return runner.CommandResult(("x",), returncode, stdout, "", False, len(stdout), timed_out, 0.1)


@pytest.mark.parametrize("returncode,stdout,expected_state", [
    (0, "5 passed in 0.1s", mf.TestState.PASSED),
    (1, "2 failed, 3 passed in 0.1s", mf.TestState.FAILED),
    (1, "1 error in 0.1s", mf.TestState.ERROR),
    (2, "5 passed in 0.1s", mf.TestState.ERROR),          # interrupted despite a clean-looking line
    (3, "INTERNALERROR", mf.TestState.ERROR),
    (4, "usage error", mf.TestState.ERROR),
    (5, "no tests ran in 0.01s", mf.TestState.ERROR),
    (0, "garbage output", mf.TestState.ERROR),
])
def test_classify_test_run(returncode, stdout, expected_state):
    state, _ = runner.classify_test_run(_result(returncode, stdout))
    assert state is expected_state


def test_classify_test_run_timeout_is_always_error_with_no_counts():
    state, counts = runner.classify_test_run(_result(None, "5 passed", timed_out=True))
    assert state is mf.TestState.ERROR and counts is None


# --- bounded logs ------------------------------------------------------------------------------------------------------------

def test_run_limited_command_bounds_captured_output_but_reports_true_total(tmp_path):
    result = runner.run_limited_command(
        ["python", "-c", "print('x' * 5000)"], cwd=tmp_path, timeout=10, max_output_bytes=100,
    )
    assert len(result.stdout) == 100 and result.truncated and result.total_bytes > 100


def test_run_limited_command_argv_no_shell(tmp_path):
    # a shell metacharacter in an argument must be treated literally, never interpreted
    result = runner.run_limited_command(["python", "-c", "import sys; print(sys.argv[1])", "$(echo pwned)"],
                                        cwd=tmp_path, timeout=10, max_output_bytes=1000)
    assert result.stdout.strip() == "$(echo pwned)"


# --- boundary detection --------------------------------------------------------------------------------------------------------

def test_boundary_violation_is_recorded_for_a_change_outside_editable_paths(config):
    def editor(wt: Path) -> None:
        edit_worktree(wt)
        write(wt / "OUTSIDE.md", "not an editable path\n")

    result = _prepare_and_edit(config, editor=editor)
    fin = runner.finalize(config, result.run_id, task_id="task-boundary")
    m = mf.load_manifest(fin.manifest_path)
    assert any("OUTSIDE.md" in e.description for e in m.measurements.boundary_violations)
    assert all(e.provenance == "observed" for e in m.measurements.boundary_violations)


# --- interruption / resume ------------------------------------------------------------------------------------------------------

def test_finalize_resumes_after_a_crash_right_after_mounting(config, monkeypatch):
    result = _prepare_and_edit(config)

    real_run = runner.run_limited_command
    calls = {"n": 0}

    def boom(*a, **kw):
        calls["n"] += 1
        raise RuntimeError("simulated crash right after mounting")

    monkeypatch.setattr(runner, "run_limited_command", boom)
    with pytest.raises(RuntimeError, match="simulated crash"):
        runner.finalize(config, result.run_id, task_id="task-resume")
    assert calls["n"] == 1
    assert (result.worktree_path / ".futurefork-evaluator" / "sample").is_dir()  # left mounted
    assert not (result.run_dir / runner.MANIFEST_FILE).exists()

    monkeypatch.setattr(runner, "run_limited_command", real_run)
    fin = runner.finalize(config, result.run_id, task_id="task-resume")  # same run_id: this IS "resume"
    assert fin.outcome is mf.Outcome.COMPLETED
    m = mf.load_manifest(fin.manifest_path)
    assert m.agent.task_id == "task-resume"
    patch = (result.run_dir / "patch.diff").read_text(encoding="utf-8")
    changed = json.loads((result.run_dir / "changed-paths.json").read_text(encoding="utf-8"))
    assert ".futurefork-evaluator" not in patch
    assert all(not row["path"].startswith(".futurefork-evaluator/") for row in changed)
    assert not m.measurements.boundary_violations


def test_finalize_rejects_a_pre_existing_mount_that_does_not_match_the_frozen_pack(config):
    result = _prepare_and_edit(config)
    write(result.worktree_path / ".futurefork-evaluator" / "sample" / "test_sample.py", "not the real pack\n")
    fin = runner.finalize(config, result.run_id, task_id="task-bad-leftover")
    m = mf.load_manifest(fin.manifest_path)
    assert m.outcome is mf.Outcome.RUNNER_ERROR
    assert "did not match" in m.outcome_detail


# --- collisions ----------------------------------------------------------------------------------------------------------------

def test_prepare_refuses_to_reuse_a_run_id(config):
    runner.prepare(config, "modular", config.repo / "scenario.yaml", run_id="20260927T090000Z-modular-sample")
    with pytest.raises(runner.RunCollisionError):
        runner.prepare(config, "modular", config.repo / "scenario.yaml", run_id="20260927T090000Z-modular-sample")


def test_finalize_of_an_unknown_run_id_is_reported_clearly(config):
    with pytest.raises(runner.RunNotFoundError):
        runner.finalize(config, "20260927T090000Z-modular-sample", task_id="x")


# --- cleanup failure preserves the exact worktree -----------------------------------------------------------------------------

def test_cleanup_failure_is_reported_and_the_worktree_is_preserved(config, monkeypatch):
    result = _prepare_and_edit(config)
    from futurefork.worktrees import CleanupError

    def boom_remove(self, wt):
        raise CleanupError("simulated cleanup failure", path=str(wt.path))

    monkeypatch.setattr("futurefork.worktrees.WorktreeManager.remove", boom_remove)
    fin = runner.finalize(config, result.run_id, task_id="task-cleanup-fail")
    assert fin.outcome is mf.Outcome.COMPLETED
    assert fin.cleanup_error is not None and "simulated cleanup failure" in fin.cleanup_error
    assert result.worktree_path.is_dir()  # preserved, not force-deleted another way

    monkeypatch.undo()
    runner.cleanup(config, result.run_id)
    assert not result.worktree_path.exists()


# --- pack never appears before finalize; no broad deletion in the runner's own source --------------------------------------------

def test_pack_is_never_present_anywhere_in_the_worktree_before_finalize_mounts_it(config):
    result = runner.prepare(config, "modular", config.repo / "scenario.yaml", run_id="20260927T090000Z-modular-sample")
    for p in result.worktree_path.rglob("*"):
        assert "futurefork-evaluator" not in str(p)


def test_no_broad_deletion_apis_in_the_runner_source():
    source = Path(runner.__file__).read_text()
    code = source.split('"""', 2)[2]  # after the module docstring
    banned = ["os.rmdir", "os.removedirs", "glob.", "fnmatch.filter", "os.walk", ".rglob(", ".iterdir(",
             "shell=True", "os.system", "os.remove("]
    for token in banned:
        assert token not in code, token
    # exactly one, tightly-scoped rmtree: an exact path this function itself just re-verified byte-for-byte
    rmtree_calls = re.findall(r"shutil\.rmtree\(([^)]*)\)", code)
    assert rmtree_calls == ["mount_dest"], rmtree_calls


# --- artifact-hashes.json / manifest match disk bytes; tamper is detectable after the fact ----------------------------------------

def test_artifact_hashes_match_disk_bytes_and_tamper_is_detectable(config):
    result = _prepare_and_edit(config)
    fin = runner.finalize(config, result.run_id, task_id="task-hash-check")
    m = mf.load_manifest(fin.manifest_path)
    patch_artifact = next(a for a in m.artifacts if a.path == "patch.diff")
    assert hashlib.sha256((result.run_dir / "patch.diff").read_bytes()).hexdigest() == patch_artifact.sha256

    (result.run_dir / "patch.diff").write_bytes((result.run_dir / "patch.diff").read_bytes() + b"TAMPERED")
    recomputed = hashlib.sha256((result.run_dir / "patch.diff").read_bytes()).hexdigest()
    assert recomputed != patch_artifact.sha256   # the recorded hash now proves tampering happened


# --- the real repository, its refs, and the P0.3 worktree are untouched (redundant with the autouse guard, explicit here) ---------

def test_fixtures_never_touch_the_production_repository_or_p03(config, tmp_path):
    assert config.repo != ROOT and ROOT not in config.repo.parents
    assert ROOT not in config.runs_root.parents
    assert not str(config.worktree_root).startswith(str(P03))
    assert config.runs_root != ROOT / "artifacts" / "runs"
