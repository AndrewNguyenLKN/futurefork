"""P0.4: the run manifest contract, its generated JSON Schema, and deterministic serialization."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from futurefork import manifest as mf
from futurefork.manifest import (
    Outcome,
    OutcomeClass,
    RunManifest,
    canonical_json,
    dump_manifest,
    load_manifest,
    loads_manifest,
    manifest_json_schema,
    manifest_sha256,
    outcome_class,
    write_manifest,
)

ROOT = Path(__file__).resolve().parents[1]


def h(label: str) -> str:
    """Deterministic synthetic SHA-256 for fixtures."""
    return hashlib.sha256(label.encode()).hexdigest()


PACK = h("frozen-pack")
COMMIT = "f9e3ecda1e4a8452678578226b2553a6ebddf536"
TREE = "1d72a1ceab01f7c0372585aa583bf3e14e9cc37a"


def artifact(path: str, kind: str, label: str | None = None, sha: str | None = None) -> dict:
    return {"path": path, "kind": kind, "sha256": sha or h(label or path), "size_bytes": 100}


def completed() -> dict:
    """A valid `completed` manifest as plain JSON data. Synthetic: not derived from any real run."""
    return {
        "schema_version": 1,
        "run_id": "20260927T003000Z-modular-partial-refund",
        "candidate": {"name": "modular", "ref": "modular", "starting_commit": COMMIT},
        "scenario": {"id": "partial-refund", "sha256": h("scenario-yaml")},
        "evaluator": {"test_pack_sha256": PACK, "observed_sha256_after_run": PACK},
        "agent": {"provider": "IBM Bob", "task_id": "d12b84c1a6a03a337b56b8594ebd6d2a", "human_triggered": True},
        "limits": {"wall_seconds": 600, "max_attempts": 4, "max_output_bytes": 1000000},
        "toolchain": {"python": "3.14.7", "pytest": "9.1.1"},
        "started_at": "2026-09-27T00:30:00Z",
        "finished_at": "2026-09-27T00:36:00Z",
        "outcome": "completed",
        "tests": {
            "regression": {"state": "passed", "command": ["python", "-m", "pytest", "-q", "tests"], "returncode": 0,
                           "passed": 68, "failed": 0, "errors": 0, "skipped": 0,
                           "results_artifact": "regression-results.xml"},
            "protected": {"state": "passed", "command": ["python", "-m", "pytest", "-q", ".futurefork-evaluator/partial_refund"],
                          "returncode": 0, "passed": 34, "failed": 0, "errors": 0, "skipped": 0,
                          "results_artifact": "test-results.json"},
        },
        "measurements": {
            "attempts": 2, "duration_seconds": 360.0, "output_bytes": 12345, "changed_files": 6,
            "lines_added": 488, "lines_deleted": 16,
            "human_interventions": [{"description": "Operator denied a compound shell command.", "provenance": "reported"}],
            "boundary_violations": [],
        },
        "ending": {"tree": TREE, "diff_artifact": "patch.diff"},
        "artifacts": [
            artifact("scenario.yaml", "scenario", sha=h("scenario-yaml")),
            artifact("task-packet.md", "task_packet"),
            artifact("patch.diff", "patch"),
            artifact("changed-paths.json", "changed_paths"),
            artifact("test-results.json", "test_results"),
            artifact("regression-results.xml", "junit_xml"),
            artifact("measurements.json", "measurements"),
            artifact("events.jsonl", "events"),
            artifact("stdout.log", "stdout_log"),
            artifact("stderr.log", "stderr_log"),
            artifact("artifact-hashes.json", "artifact_hashes"),
        ],
    }


def with_(data: dict, path: str, value) -> dict:
    """Deep copy of `data` with the dotted `path` replaced (or removed if value is a sentinel)."""
    out = copy.deepcopy(data)
    node = out
    *parents, leaf = path.split(".")
    for key in parents:
        node = node[int(key)] if isinstance(node, list) else node[key]
    if isinstance(node, list):
        node[int(leaf)] = value
    elif value is REMOVE:
        del node[leaf]
    else:
        node[leaf] = value
    return out


REMOVE = object()


def with_extra(data: dict) -> dict:
    """Add one spare artifact (index 10) that no other field references."""
    out = copy.deepcopy(data)
    out["artifacts"].append(artifact("spare.txt", "other"))
    return out


def parse(data: dict) -> RunManifest:
    return loads_manifest(json.dumps(data))


def rejects(data: dict, match: str | None = None) -> None:
    with pytest.raises(ValidationError, match=match):
        parse(data)


# --- outcome fixtures ---------------------------------------------------------------------------

def _tests(reg: str, prot: str) -> dict:
    counts = {
        "passed": {"returncode": 0, "passed": 10, "failed": 0, "errors": 0, "skipped": 0},
        "failed": {"returncode": 1, "passed": 8, "failed": 2, "errors": 0, "skipped": 0},
        "error": {"returncode": 2, "passed": 0, "failed": 0, "errors": 1, "skipped": 0},
        "not_run": {},
    }
    cmd = {"command": ["python", "-m", "pytest", "-q"]}
    return {
        "regression": {"state": reg, **({} if reg == "not_run" else cmd), **counts[reg]},
        "protected": {"state": prot, **({} if prot == "not_run" else cmd), **counts[prot]},
    }


def outcome_manifest(outcome: str) -> dict:
    d = completed()
    d["outcome"] = outcome
    if outcome == "completed":
        return d
    d.pop("ending") if outcome not in ("regression_failed", "acceptance_failed") else None
    if outcome == "acceptance_failed":
        d["tests"] = _tests("passed", "failed")
    elif outcome == "regression_failed":
        d["tests"] = _tests("failed", "not_run")
    elif outcome == "budget_exhausted":
        d["tests"] = _tests("passed", "failed")
        d["measurements"]["attempts"] = 4
    elif outcome == "oracle_tampered":
        d["tests"] = _tests("passed", "not_run")
        d["evaluator"]["observed_sha256_after_run"] = h("tampered-pack")
        d["outcome_detail"] = "Pack hash differs from the frozen hash; tests were not run."
    elif outcome in ("candidate_invalid", "setup_failed"):
        d["tests"] = _tests("not_run", "not_run")
        d["agent"]["task_id"] = None
        d["measurements"].update(attempts=0, duration_seconds=1.5)
        d["evaluator"]["observed_sha256_after_run"] = None
        d["outcome_detail"] = "Dependency setup exited with status 2 before any agent work."
        d["finished_at"] = None
    elif outcome == "runner_error":
        d["tests"] = _tests("passed", "error")
        d["outcome_detail"] = "Runner lost the worktree while executing protected tests."
    return d


ALL_OUTCOMES = [o.value for o in Outcome]


# --- valid manifests and round trips --------------------------------------------------------------

def test_completed_manifest_round_trips_without_loss():
    m = parse(completed())
    again = loads_manifest(dump_manifest(m))
    assert again == m
    assert dump_manifest(again) == dump_manifest(m)
    assert canonical_json(again) == canonical_json(m)
    assert again.model_dump(mode="json") == m.model_dump(mode="json")


@pytest.mark.parametrize("outcome", ALL_OUTCOMES)
def test_every_outcome_has_a_valid_representation(outcome):
    m = parse(outcome_manifest(outcome))
    assert m.outcome.value == outcome
    assert loads_manifest(dump_manifest(m)) == m


def test_completed_manifest_validates_against_the_generated_json_schema():
    validator = Draft202012Validator(manifest_json_schema(), format_checker=FormatChecker())
    validator.validate(json.loads(dump_manifest(parse(completed()))))
    validator.validate(completed())


@pytest.mark.parametrize("outcome", ALL_OUTCOMES)
def test_every_outcome_fixture_is_schema_valid(outcome):
    Draft202012Validator(manifest_json_schema(), format_checker=FormatChecker()).validate(
        json.loads(dump_manifest(parse(outcome_manifest(outcome))))
    )


def test_optional_end_of_run_fields_may_be_absent_for_infrastructure_outcomes():
    d = outcome_manifest("setup_failed")
    assert d["finished_at"] is None and "ending" not in d
    m = parse(d)
    assert m.finished_at is None and m.ending is None


def test_models_are_frozen():
    m = parse(completed())
    with pytest.raises(ValidationError):
        m.outcome = Outcome.RUNNER_ERROR
    with pytest.raises(ValidationError):
        m.candidate.ref = "coupled"


# --- deterministic serialization ------------------------------------------------------------------

def test_serialization_is_key_sorted_ascii_and_newline_terminated():
    m = parse(with_(completed(), "measurements.human_interventions.0.description", "caf\u00e9 \u2013 note"))
    text = dump_manifest(m)
    assert text.endswith("}\n") and text.isascii() and "\\u00e9" in text
    data = json.loads(text)
    assert list(data) == sorted(data)
    assert list(data["tests"]) == sorted(data["tests"])
    assert loads_manifest(text) == m


def test_semantically_equal_inputs_serialize_identically_and_hash_equal():
    a = completed()
    b = dict(reversed(list(completed().items())))              # different key order
    b["started_at"] = "2026-09-27T00:30:00+00:00"              # different UTC spelling
    b["finished_at"] = "2026-09-27T00:36:00+00:00"
    ma, mb = parse(a), parse(b)
    assert dump_manifest(ma) == dump_manifest(mb)
    assert manifest_sha256(ma) == manifest_sha256(mb) == hashlib.sha256(canonical_json(ma).encode()).hexdigest()
    assert '"started_at":"2026-09-27T00:30:00Z"' in canonical_json(ma)


def test_hash_changes_when_any_content_changes():
    base = manifest_sha256(parse(completed()))
    assert manifest_sha256(parse(with_(completed(), "measurements.attempts", 3))) != base
    assert manifest_sha256(parse(with_(completed(), "toolchain.pytest", "9.1.2"))) != base


def test_write_manifest_is_exclusive_and_reloadable(tmp_path):
    m = parse(completed())
    target = tmp_path / "manifest.json"
    write_manifest(m, target)
    assert target.read_text() == dump_manifest(m) and load_manifest(target) == m
    with pytest.raises(FileExistsError):
        write_manifest(m, target)
    assert load_manifest(target) == m


# --- JSON Schema is generated, checked in, and consistent with the model ---------------------------

def test_checked_in_schema_matches_model_generated_schema_byte_for_byte():
    assert mf.SCHEMA_PATH.read_text(encoding="utf-8") == mf.schema_text()
    assert json.loads(mf.SCHEMA_PATH.read_text()) == manifest_json_schema()


def test_schema_generation_is_deterministic():
    assert mf.schema_text() == mf.schema_text()


def test_schema_check_command_passes_and_detects_drift(tmp_path, monkeypatch):
    ok = subprocess.run([sys.executable, "-m", "futurefork.manifest", "schema", "--check"], cwd=ROOT, capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr
    stale = tmp_path / "schema.json"
    stale.write_text(mf.schema_text().replace('"RunManifest"', '"Drifted"'))
    monkeypatch.setattr(mf, "SCHEMA_PATH", stale)
    assert mf._main(["schema", "--check"]) == 1


def test_schema_declares_dialect_and_forbids_extra_properties_everywhere():
    schema = manifest_json_schema()
    assert schema["$schema"] == mf.JSON_SCHEMA_DIALECT
    Draft202012Validator.check_schema(schema)
    for name, definition in [("RunManifest", schema), *schema["$defs"].items()]:
        if definition.get("type") == "object":
            assert definition.get("additionalProperties") is False, name


def test_schema_enumerates_exactly_the_architecture_taxonomy():
    schema = manifest_json_schema()
    assert sorted(schema["$defs"]["Outcome"]["enum"]) == sorted(taxonomy_from_architecture_doc())
    assert sorted(schema["$defs"]["TestState"]["enum"]) == ["error", "failed", "not_run", "passed"]


def taxonomy_from_architecture_doc() -> list[str]:
    text = (ROOT / "docs" / "ARCHITECTURE.md").read_text()
    section = text.split("## Failure taxonomy", 1)[1].split("\n## ", 1)[0]
    return re.findall(r"^- `([a-z_]+)`:", section, re.M)


def test_outcome_enum_matches_architecture_doc():
    assert sorted(o.value for o in Outcome) == sorted(taxonomy_from_architecture_doc())
    assert len(taxonomy_from_architecture_doc()) == 8


STRUCTURAL_MUTATIONS = {
    "unknown top-level field": lambda d: {**d, "score": 0.9},
    "unknown nested field": lambda d: with_(d, "candidate.extra", "x"),
    "uppercase scenario hash": lambda d: with_(d, "scenario.sha256", "A" * 64),
    "short pack hash": lambda d: with_(d, "evaluator.test_pack_sha256", "a" * 63),
    "short commit": lambda d: with_(d, "candidate.starting_commit", "a" * 39),
    "bad outcome": lambda d: with_(d, "outcome", "won"),
    "bad test state": lambda d: with_(d, "tests.regression.state", "skipped"),
    "parent-dir artifact": lambda d: with_(d, "artifacts.2.path", "../patch.diff"),
    "absolute artifact": lambda d: with_(d, "artifacts.2.path", "/tmp/patch.diff"),
    "wrong provider": lambda d: with_(d, "agent.provider", "Other"),
    "zero limit": lambda d: with_(d, "limits.wall_seconds", 0),
    "missing required": lambda d: with_(d, "tests", REMOVE),
    "wrong schema version": lambda d: with_(d, "schema_version", 2),
}


@pytest.mark.parametrize("name", sorted(STRUCTURAL_MUTATIONS))
def test_structural_errors_are_rejected_by_both_schema_and_model(name):
    mutated = STRUCTURAL_MUTATIONS[name](completed())
    validator = Draft202012Validator(manifest_json_schema(), format_checker=FormatChecker())
    assert not validator.is_valid(mutated), "JSON Schema accepted it"
    rejects(mutated)


def test_json_schema_alone_cannot_check_invariants_so_load_manifest_is_required():
    """Documented limitation: these pass the schema but the model refuses them."""
    validator = Draft202012Validator(manifest_json_schema(), format_checker=FormatChecker())
    bad = with_(completed(), "tests.protected", {"state": "failed", "command": ["pytest"], "returncode": 1})
    assert validator.is_valid(bad)
    rejects(bad, "completed requires")


# --- unknown fields, hashes, commits, refs, identifiers ---------------------------------------------------

@pytest.mark.parametrize(
    "path",
    ["candidate", "scenario", "evaluator", "agent", "limits", "tests", "tests.regression", "tests.protected",
     "measurements", "ending", "artifacts.0", "measurements.human_interventions.0"],
)
def test_unknown_fields_are_rejected_at_every_level(path):
    d = completed()
    node = d
    for key in path.split("."):
        node = node[int(key)] if isinstance(node, list) else node[key]
    node["surprise"] = 1
    rejects(d, "surprise")


@pytest.mark.parametrize("bad", ["A" * 64, "a" * 63, "a" * 65, "g" * 64, "", " " + "a" * 63, "a" * 63 + "\n", "0x" + "a" * 62])
def test_sha256_must_be_64_lowercase_hex(bad):
    for path in ("scenario.sha256", "evaluator.test_pack_sha256", "evaluator.observed_sha256_after_run", "artifacts.0.sha256"):
        rejects(with_(completed(), path, bad))


@pytest.mark.parametrize("bad", ["A" * 40, "a" * 39, "a" * 41, "f9e3ecd", "g" * 40, "a" * 63 + "\n", COMMIT + " ", "HEAD"])
def test_git_object_ids_must_be_full_lowercase_hex(bad):
    rejects(with_(completed(), "candidate.starting_commit", bad))
    rejects(with_(completed(), "ending.tree", bad))
    rejects(with_(with_(completed(), "ending.commit", bad), "ending.tree", TREE))


def test_ref_is_a_name_and_a_commit_id_is_not_a_ref():
    for commit_like in (COMMIT, "a" * 40, "a" * 64):
        rejects(with_(completed(), "candidate.ref", commit_like))
    ok = parse(with_(completed(), "candidate.ref", "refs/heads/modular"))
    assert ok.candidate.ref != ok.candidate.starting_commit
    assert parse(with_(completed(), "candidate.ref", "feature/abc-123_x.y")).candidate.ref == "feature/abc-123_x.y"
    # a 40-char string that is NOT pure lowercase hex is a legal branch name, not a commit id
    assert parse(with_(completed(), "candidate.ref", "g" * 40)).candidate.ref == "g" * 40


@pytest.mark.parametrize("bad", ["", "-x", "/x", ".x", "x/", "x.", "a..b", "a//b", "x.lock", "a/x.lock/b", "a b", "a~b", "a^b", "a:b", "a\\b", "x" * 201, "réf"])
def test_unsafe_refs_are_rejected(bad):
    rejects(with_(completed(), "candidate.ref", bad))


@pytest.mark.parametrize("bad", ["Modular", "1abc", "a_b", "a--", "-a", "a b", ""])
def test_candidate_name_and_scenario_id_patterns(bad):
    rejects(with_(completed(), "candidate.name", bad))
    rejects(with_(completed(), "scenario.id", bad))


def test_task_id_pattern_and_provider():
    rejects(with_(completed(), "agent.task_id", "short"))
    rejects(with_(completed(), "agent.task_id", "has space in it 1234"))
    assert parse(outcome_manifest("runner_error")).agent.provider == "IBM Bob"


# --- run id and timestamps ---------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "run_id",
    ["20260927T003000Z-coupled-partial-refund", "20260927T003000Z-modular-ordered-discounts",
     "20260927T003001Z-modular-partial-refund", "20260927T003000-modular-partial-refund", "modular-partial-refund",
     "20260927T003000Z-modular-partial-refund-2", "20260927T003000Z-Modular-partial-refund", "20260927T003000Z-modular-partial-refund/../x"],
)
def test_run_id_must_match_time_candidate_and_scenario(run_id):
    rejects(with_(completed(), "run_id", run_id))


@pytest.mark.parametrize(
    "value",
    ["2026-09-27T00:30:00+08:00", "2026-09-27T00:30:00", "2026-09-27T00:30:00.5Z", "2026-09-27", "", "yesterday"],
)
def test_timestamps_must_be_utc_whole_seconds(value):
    rejects(with_(completed(), "started_at", value))


def test_finished_must_not_precede_started_and_is_required_where_evidence_exists():
    rejects(with_(completed(), "finished_at", "2026-09-27T00:29:59Z"), "precedes")
    rejects(with_(completed(), "finished_at", None), "requires finished_at")
    assert parse(with_(completed(), "finished_at", "2026-09-27T00:30:00Z")).finished_at == parse(completed()).started_at


# --- artifacts ----------------------------------------------------------------------------------------------------

UNSAFE_PATHS = [
    "/etc/passwd", "../x", "a/../b", "a/..", "..", ".", "./a", "a/./b", "a//b", "a/", "", "//a", "a\\b", "..\\x",
    "C:/x", "C:\\x", "~/x", "a b", "a\tb", "a\nb", "a\x00b", "%2e%2e/x", "a/%2e%2e/b", "\u2025/x", "\uff0e\uff0e/x", "x" * 241,
    "manifest.json", "a;b", "a*b", "file:///x", "-rf/x" + "\u200b",
]


@pytest.mark.parametrize("path", UNSAFE_PATHS)
def test_unsafe_artifact_paths_are_rejected(path):
    d = with_(with_extra(completed()), "artifacts.10.path", path)
    validator = Draft202012Validator(manifest_json_schema(), format_checker=FormatChecker())
    rejects(d)
    if path != "manifest.json":  # that rule is a model rule, not expressible as a shape
        assert not validator.is_valid(d)


@pytest.mark.parametrize("path", ["logs/stdout.log", "a/b/c.txt", "..hidden", "...", "a.b-c_d/e", "run-1/patch_v2.diff"])
def test_safe_relative_posix_paths_are_accepted(path):
    d = with_(with_extra(completed()), "artifacts.10.path", path)
    assert parse(d).artifacts[10].path == path


def test_duplicate_artifact_paths_are_rejected_exactly_and_case_insensitively():
    dup = completed()
    dup["artifacts"].append(artifact("patch.diff", "patch"))
    rejects(dup, "duplicate artifact path")
    case = completed()
    case["artifacts"].append(artifact("PATCH.DIFF", "other"))
    rejects(case, "duplicate artifact path")


def test_a_path_cannot_be_both_a_file_and_a_directory():
    d = completed()
    d["artifacts"].append(artifact("patch.diff/inner.txt", "other"))
    rejects(d, "both a file and a directory")


def test_artifact_size_and_kind_are_validated():
    rejects(with_(completed(), "artifacts.0.size_bytes", -1))
    rejects(with_(completed(), "artifacts.0.size_bytes", "10"))
    rejects(with_(completed(), "artifacts.0.kind", "binary"))
    assert parse(with_(completed(), "artifacts.0.size_bytes", 0)).artifacts[0].size_bytes == 0


def test_scenario_artifact_must_carry_the_scenario_hash():
    rejects(with_(completed(), "artifacts.0.sha256", h("edited-yaml")), "scenario artifact")


def test_cross_references_must_resolve_to_listed_artifacts():
    rejects(with_(completed(), "ending.diff_artifact", "missing.diff"), "not listed")
    rejects(with_(completed(), "ending.diff_artifact", "events.jsonl"), "must have kind patch")
    rejects(with_(completed(), "tests.protected.results_artifact", "nope.json"), "not listed")
    d = with_(completed(), "measurements.boundary_violations", [{"description": "probed system paths", "provenance": "reported", "evidence": "gone.log"}])
    rejects(d, "not listed")
    ok = with_(completed(), "measurements.boundary_violations", [{"description": "probed system paths", "provenance": "reported", "evidence": "events.jsonl"}])
    assert parse(ok).measurements.boundary_violations[0].evidence == "events.jsonl"


# --- test-state invariants -------------------------------------------------------------------------------------------------

def run(**kw) -> dict:
    base = {"state": "passed", "command": ["pytest"], "returncode": 0, "passed": 5, "failed": 0, "errors": 0, "skipped": 0}
    base.update(kw)
    return {k: v for k, v in base.items() if v is not REMOVE}


@pytest.mark.parametrize(
    "test_run,message",
    [
        ({"state": "not_run", "passed": 1}, "not_run"),
        ({"state": "not_run", "returncode": 0}, "not_run"),
        ({"state": "not_run", "results_artifact": "test-results.json"}, "not_run"),
        (run(failed=1), "requires passed >= 1"),
        (run(errors=1), "requires passed >= 1"),
        (run(passed=0), "requires passed >= 1"),
        (run(returncode=1), "non-zero returncode"),
        (run(state="failed", failed=0, returncode=1), "failed >= 1"),
        (run(passed=3, failed=REMOVE), "given together"),
        (run(state="error", passed=0, failed=2, errors=0, returncode=1), "only failed tests"),
        (run(passed=-1), None),
    ],
)
def test_test_run_state_must_match_its_evidence(test_run, message):
    rejects(with_(outcome_manifest("acceptance_failed"), "tests.regression", test_run), message)


def test_states_passed_failed_error_not_run_are_all_representable():
    assert parse(with_(completed(), "tests.regression", run(results_artifact="regression-results.xml"))).tests.regression.state.value == "passed"
    assert parse(outcome_manifest("acceptance_failed")).tests.protected.state.value == "failed"
    assert parse(outcome_manifest("runner_error")).tests.protected.state.value == "error"
    assert parse(outcome_manifest("regression_failed")).tests.protected.state.value == "not_run"
    # error without counts (the tests never produced a result) is legal
    assert parse(with_(outcome_manifest("runner_error"), "tests.protected", {"state": "error", "command": ["pytest"]})).tests.protected.has_counts is False


# --- outcome invariants ----------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("reg,prot", [("failed", "passed"), ("passed", "failed"), ("passed", "error"), ("passed", "not_run"), ("not_run", "passed"), ("error", "passed")])
def test_completed_requires_both_runs_passed(reg, prot):
    d = completed()
    d["tests"] = _tests(reg, prot)
    rejects(d, "completed requires regression and protected to be passed")


@pytest.mark.parametrize(
    "path,value,message",
    [
        ("evaluator.observed_sha256_after_run", h("other"), "observed pack hash"),
        ("evaluator.observed_sha256_after_run", None, "observed pack hash"),
        ("agent.task_id", None, "task_id"),
        ("measurements.attempts", None, "attempts"),
        ("measurements.attempts", 0, "attempts"),
        ("measurements.attempts", 5, "attempts"),
        ("measurements.duration_seconds", None, "duration"),
        ("measurements.duration_seconds", 601.0, "wall_seconds"),
        ("measurements.output_bytes", 1000001, "max_output_bytes"),
        ("ending", None, "ending.diff_artifact"),
        ("ending", {"diff_artifact": "patch.diff"}, "commit or tree"),
        ("ending", {"tree": TREE}, "diff_artifact"),
        ("outcome_detail", "all fine", "no outcome_detail"),
        ("finished_at", None, "finished_at"),
        ("tests.regression.passed", None, "given together"),
        ("tests.protected", {"state": "passed", "command": ["pytest"], "returncode": 0}, "test counts"),
    ],
)
def test_completed_requires_its_evidence(path, value, message):
    rejects(with_(completed(), path, value), message)


def test_completed_accepts_boundary_values():
    d = with_(with_(completed(), "measurements.attempts", 4), "measurements.duration_seconds", 600.0)
    d = with_(d, "measurements.output_bytes", 1000000)
    assert parse(d).measurements.attempts == 4


def test_oracle_tampered_can_never_show_protected_passed():
    d = outcome_manifest("oracle_tampered")
    d["tests"]["protected"] = run()
    rejects(d, "cannot record protected as passed")
    parse(with_(d, "tests.protected", {"state": "not_run"}))
    parse(with_(d, "tests.protected", run(state="failed", returncode=1, passed=1, failed=1)))
    parse(with_(d, "tests.protected", {"state": "error", "command": ["pytest"]}))


def test_oracle_tampered_needs_a_differing_observed_hash_and_detail():
    rejects(with_(outcome_manifest("oracle_tampered"), "evaluator.observed_sha256_after_run", PACK), "differs from the frozen")
    rejects(with_(outcome_manifest("oracle_tampered"), "evaluator.observed_sha256_after_run", None), "differs from the frozen")
    rejects(with_(outcome_manifest("oracle_tampered"), "outcome_detail", None), "requires outcome_detail")


@pytest.mark.parametrize("outcome", ["completed", "acceptance_failed", "regression_failed", "budget_exhausted"])
def test_a_changed_pack_hash_cannot_hide_behind_a_non_tampered_outcome(outcome):
    d = outcome_manifest(outcome)
    d["evaluator"]["observed_sha256_after_run"] = h("tampered")
    rejects(d)


@pytest.mark.parametrize("outcome", ["candidate_invalid", "setup_failed", "runner_error"])
@pytest.mark.parametrize("bad_test", ["protected", "regression"])
def test_infrastructure_outcomes_never_record_a_failed_test(outcome, bad_test):
    d = outcome_manifest(outcome)
    d["tests"][bad_test] = run(state="failed", returncode=1, passed=1, failed=1)
    rejects(d, "infrastructure outcome cannot record a failed test")


@pytest.mark.parametrize("outcome", ["candidate_invalid", "setup_failed"])
@pytest.mark.parametrize(
    "path,value",
    [("agent.task_id", "d12b84c1a6a03a337b56b8594ebd6d2a"), ("measurements.attempts", 1),
     ("tests.regression", run()), ("tests.protected", run(state="error", passed=0, errors=1))],
)
def test_failures_before_agent_work_have_no_task_no_attempts_and_no_test_runs(outcome, path, value):
    rejects(with_(outcome_manifest(outcome), path, value))


@pytest.mark.parametrize("outcome", ["candidate_invalid", "setup_failed", "runner_error", "oracle_tampered"])
def test_infrastructure_and_integrity_outcomes_require_a_reason(outcome):
    rejects(with_(outcome_manifest(outcome), "outcome_detail", None), "requires outcome_detail")
    rejects(with_(outcome_manifest(outcome), "outcome_detail", ""))


def test_regression_failed_and_acceptance_failed_require_their_test_states():
    rejects(with_(outcome_manifest("regression_failed"), "tests.regression", run()), "regression_failed requires")
    rejects(with_(outcome_manifest("regression_failed"), "tests.regression", {"state": "error", "command": ["pytest"]}), "regression_failed requires")
    rejects(with_(outcome_manifest("acceptance_failed"), "tests.protected", run()), "acceptance_failed requires")
    rejects(with_(outcome_manifest("acceptance_failed"), "tests.regression", run(state="failed", returncode=1, passed=1, failed=1)), "acceptance_failed requires")
    rejects(with_(outcome_manifest("acceptance_failed"), "tests.protected", {"state": "not_run"}), "acceptance_failed requires")
    rejects(with_(outcome_manifest("acceptance_failed"), "ending", None), "ending.diff_artifact")
    rejects(with_(outcome_manifest("regression_failed"), "ending", None), "ending.diff_artifact")


def test_budget_exhausted_needs_a_measurement_that_reached_its_limit():
    d = outcome_manifest("budget_exhausted")
    rejects(with_(d, "measurements.attempts", 3), "reached its limit")
    parse(with_(with_(d, "measurements.attempts", 3), "measurements.duration_seconds", 600.0))
    parse(with_(with_(d, "measurements.attempts", 3), "measurements.output_bytes", 1000000))
    rejects(with_(d, "tests", _tests("passed", "passed")), "both test runs as passed")


def test_infrastructure_outcomes_are_classified_apart_from_candidate_evidence():
    assert {o for o in Outcome if outcome_class(o) is OutcomeClass.INFRASTRUCTURE} == {
        Outcome.CANDIDATE_INVALID, Outcome.SETUP_FAILED, Outcome.RUNNER_ERROR}
    assert outcome_class(Outcome.ORACLE_TAMPERED) is OutcomeClass.INTEGRITY
    assert {o for o in Outcome if outcome_class(o) is OutcomeClass.EXPERIMENTAL} == {
        Outcome.COMPLETED, Outcome.ACCEPTANCE_FAILED, Outcome.REGRESSION_FAILED, Outcome.BUDGET_EXHAUSTED}
    assert set(mf.OUTCOME_CLASS) == set(Outcome)


# --- measurements have no score --------------------------------------------------------------------------------------------------------------

def test_measurements_are_raw_observations_and_no_field_is_a_score():
    fields = set(mf.Measurements.model_fields)
    assert fields == {"attempts", "duration_seconds", "output_bytes", "changed_files", "lines_added", "lines_deleted",
                      "human_interventions", "boundary_violations"}
    names = json.dumps(manifest_json_schema())
    for word in ("score", "rank", "rating", "maintainab", "quality"):
        assert not re.search(rf'"[^"]*{word}[^"]*":', names, re.I), word
    rejects(with_(completed(), "measurements.maintainability_score", 0.9), "maintainability_score")


def test_measurement_values_are_validated():
    for path, bad in [("measurements.attempts", -1), ("measurements.duration_seconds", -0.1), ("measurements.lines_added", -3),
                      ("measurements.output_bytes", 1.5)]:
        rejects(with_(completed(), path, bad))
    rejects(with_(completed(), "measurements.human_interventions.0.provenance", "verified"))
    rejects(with_(completed(), "measurements.human_interventions.0.description", ""))
    rejects(with_(completed(), "measurements.human_interventions.0.description", "x" * 501))


def test_toolchain_is_an_allowlist_shaped_mapping_not_an_environment_dump():
    rejects(with_(completed(), "toolchain", {"PATH": "/usr/bin"}))
    rejects(with_(completed(), "toolchain", {"python": "x" * 201}))
    assert parse(with_(completed(), "toolchain", {})).toolchain == {}


# --- strict loading ------------------------------------------------------------------------------------------------------------------------------

def test_loader_rejects_duplicate_keys():
    text = dump_manifest(parse(completed())).replace('"outcome": "completed"', '"outcome": "completed", "outcome": "runner_error"')
    with pytest.raises(ValueError, match="duplicate JSON object keys"):
        loads_manifest(text)


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_loader_rejects_non_finite_numbers(constant):
    text = dump_manifest(parse(completed())).replace('"duration_seconds": 360.0', f'"duration_seconds": {constant}')
    with pytest.raises(ValueError):
        loads_manifest(text)


@pytest.mark.parametrize(
    "path,value",
    [("measurements.attempts", "2"), ("measurements.attempts", True), ("agent.human_triggered", "true"),
     ("agent.human_triggered", 1), ("limits.wall_seconds", "600"), ("schema_version", "1"), ("schema_version", True)],
)
def test_loader_does_not_coerce_types(path, value):
    rejects(with_(completed(), path, value))


@pytest.mark.parametrize("text", ["", "[]", "null", '"x"', "{", dump_manifest(parse(completed())) + "{}", "{} trailing"])
def test_loader_rejects_non_manifest_documents(text):
    with pytest.raises(ValueError):
        loads_manifest(text)


def test_integer_valued_seconds_are_accepted_and_normalized():
    m = parse(with_(completed(), "measurements.duration_seconds", 360))
    assert m.measurements.duration_seconds == 360.0
    assert '"duration_seconds": 360.0' in dump_manifest(m)


# --- review fixes: returncode contradictions, results kinds, completed evidence bundle ---------------------

@pytest.mark.parametrize("state,extra", [
    ("failed", {"passed": 3, "failed": 2, "errors": 0, "skipped": 0}),   # counts show failures but returncode says success
    ("failed", {}),                                                         # no counts at all
    ("error", {}),                                                          # error with no counts, still not returncode 0
    ("error", {"passed": 0, "failed": 0, "errors": 1, "skipped": 0}),
])
@pytest.mark.parametrize("path", ["tests.regression", "tests.protected"])
def test_failed_and_error_states_reject_an_explicit_returncode_of_zero(path, state, extra):
    bad = {"state": state, "command": ["pytest"], "returncode": 0, **extra}
    rejects(with_(outcome_manifest("acceptance_failed"), path, bad), f"state {state} conflicts with returncode 0")


@pytest.mark.parametrize("state,extra", [
    ("failed", {"passed": 3, "failed": 2, "errors": 0, "skipped": 0}),
    ("error", {"passed": 0, "failed": 0, "errors": 1, "skipped": 0}),
    ("error", {}),
])
@pytest.mark.parametrize("returncode", [1, 2, 5, 137, -9, None])
def test_failed_and_error_with_a_non_zero_or_absent_returncode_remain_valid(state, extra, returncode):
    good = {"state": state, "command": ["pytest"], **extra}
    if returncode is not None:
        good["returncode"] = returncode
    d = outcome_manifest("runner_error" if state == "error" else "acceptance_failed")
    m = parse(with_(d, "tests.protected", good))
    assert m.tests.protected.state.value == state


def test_passed_still_rejects_any_non_zero_returncode_and_accepts_zero_or_absent():
    for rc in (1, 2, -1):
        rejects(with_(completed(), "tests.protected.returncode", rc), "non-zero returncode")
    assert parse(with_(outcome_manifest("acceptance_failed"), "tests.regression", run(returncode=REMOVE))).tests.regression.returncode is None


@pytest.mark.parametrize("bad_path,kind", [("events.jsonl", "events"), ("patch.diff", "patch"), ("task-packet.md", "task_packet"),
                                            ("stdout.log", "stdout_log"), ("scenario.yaml", "scenario")])
@pytest.mark.parametrize("field", ["tests.protected.results_artifact", "tests.regression.results_artifact"])
def test_results_artifact_must_be_test_results_or_junit(field, bad_path, kind):
    rejects(with_(completed(), field, bad_path), r"must have kind test_results or junit_xml")


@pytest.mark.parametrize("good_path", ["test-results.json", "regression-results.xml"])
@pytest.mark.parametrize("field", ["tests.protected.results_artifact", "tests.regression.results_artifact"])
def test_results_artifact_accepts_test_results_and_junit(field, good_path):
    assert parse(with_(completed(), field, good_path)).artifacts


def test_results_artifact_kind_is_also_checked_outside_completed():
    d = with_(outcome_manifest("acceptance_failed"), "tests.protected.results_artifact", "events.jsonl")
    rejects(d, "must have kind test_results or junit_xml")
    assert parse(with_(outcome_manifest("acceptance_failed"), "tests.protected.results_artifact", "test-results.json"))


def test_results_artifact_must_still_be_listed():
    rejects(with_(completed(), "tests.protected.results_artifact", "unlisted.json"), "not listed")


REQUIRED_KINDS = ["scenario", "task_packet", "patch", "changed_paths", "test_results", "measurements", "events",
                  "stdout_log", "stderr_log", "artifact_hashes"]


@pytest.mark.parametrize("kind", REQUIRED_KINDS)
def test_completed_requires_every_kind_in_the_evidence_bundle(kind):
    d = completed()
    d["artifacts"] = [a for a in d["artifacts"] if a["kind"] != kind]
    # Keep cross-references consistent so only the bundle rule can fire.
    listed = {a["path"] for a in d["artifacts"]}
    for path in ("tests.protected.results_artifact",):
        if d["tests"]["protected"]["results_artifact"] not in listed:
            d["tests"]["protected"]["results_artifact"] = "regression-results.xml"
    if d["ending"]["diff_artifact"] not in listed:
        d["ending"]["diff_artifact"] = "task-packet.md"
    with pytest.raises(ValidationError) as info:
        parse(d)
    assert "evidence bundle" in str(info.value) or "must have kind" in str(info.value)
    if kind in {"scenario", "task_packet", "changed_paths", "measurements", "events", "stdout_log", "stderr_log", "artifact_hashes"}:
        assert f"'{kind}'" in str(info.value)


def test_completed_bundle_error_lists_all_missing_kinds():
    d = completed()
    d["artifacts"] = [a for a in d["artifacts"] if a["kind"] not in ("events", "stdout_log", "stderr_log")]
    with pytest.raises(ValidationError, match=r"missing artifact kinds: \['events', 'stdout_log', 'stderr_log'\]"):
        parse(d)


def test_completed_with_only_a_patch_and_self_reported_counts_is_rejected():
    """The review's counterexample: counts alone are not evidence."""
    d = completed()
    d["artifacts"] = [a for a in d["artifacts"] if a["kind"] in ("patch", "test_results", "junit_xml")]
    d["tests"]["protected"]["results_artifact"] = "test-results.json"
    rejects(d, "evidence bundle")
    d2 = completed()
    d2["artifacts"] = [a for a in d2["artifacts"] if a["kind"] == "patch"]
    d2["tests"]["protected"].pop("results_artifact")
    d2["tests"]["regression"].pop("results_artifact")
    rejects(d2)


@pytest.mark.parametrize("field", ["tests.regression.results_artifact", "tests.protected.results_artifact"])
def test_completed_requires_a_results_artifact_for_each_test_run(field):
    rejects(with_(completed(), field, None), "results_artifact")


@pytest.mark.parametrize("field,value,message", [
    ("tests.regression.returncode", None, "command and returncode 0"),
    ("tests.protected.returncode", None, "command and returncode 0"),
    ("tests.regression.command", None, "command and returncode 0"),
    ("tests.protected.command", [], "command and returncode 0"),
])
def test_completed_requires_each_test_run_to_record_command_and_returncode_zero(field, value, message):
    rejects(with_(completed(), field, value), message)


def test_one_results_file_may_serve_both_runs_and_extra_artifacts_are_allowed():
    d = with_(completed(), "tests.regression.results_artifact", "test-results.json")
    d["artifacts"].append(artifact("notes/extra.md", "notes"))
    assert parse(d)


def test_the_bundle_rule_applies_to_completed_only():
    """Other outcomes keep only the evidence their own invariants require (e.g. a diff), so failures stay recordable."""
    d = outcome_manifest("acceptance_failed")
    d["artifacts"] = [a for a in d["artifacts"] if a["kind"] in ("patch", "test_results", "junit_xml")]
    assert parse(d).outcome is Outcome.ACCEPTANCE_FAILED
    d = outcome_manifest("setup_failed")
    d["artifacts"] = [artifact("stderr.log", "stderr_log")]
    assert parse(d).outcome is Outcome.SETUP_FAILED



# --- found while starting P0.5: `$` also matches before a trailing newline -----------------------------------

def _component(model, **kw):
    return model.model_validate(kw)


# Each entry pairs a field with a value that IS valid for that field alone (verified below), so the
# newline case is a controlled one-character mutation of a known-accepted value, not a guess.
NEWLINE_CASES = [
    ("ref", lambda v: _component(mf.Candidate, name="modular", ref=v, starting_commit=COMMIT), "modular"),
    ("candidate-name", lambda v: _component(mf.Candidate, name=v, ref="modular", starting_commit=COMMIT), "modular"),
    ("starting-commit", lambda v: _component(mf.Candidate, name="modular", ref="modular", starting_commit=v), COMMIT),
    ("scenario-id", lambda v: _component(mf.ScenarioRef, id=v, sha256=h("x")), "partial-refund"),
    ("scenario-sha", lambda v: _component(mf.ScenarioRef, id="partial-refund", sha256=v), h("x")),
    ("pack-sha", lambda v: _component(mf.Evaluator, test_pack_sha256=v), PACK),
    ("tree", lambda v: _component(mf.Ending, tree=v), TREE),
    ("diff-path", lambda v: _component(mf.Ending, diff_artifact=v), "patch.diff"),
    ("task-id", lambda v: _component(mf.Agent, provider="IBM Bob", task_id=v, human_triggered=True),
     "d12b84c1a6a03a337b56b8594ebd6d2a"),
    ("artifact-path", lambda v: _component(mf.Artifact, path=v, kind="patch", sha256=h("x"), size_bytes=1), "patch.diff"),
]


@pytest.mark.parametrize("build,good", [(b, g) for _, b, g in NEWLINE_CASES], ids=[c[0] for c in NEWLINE_CASES])
def test_no_pattern_accepts_a_trailing_newline_in_isolation(build, good):
    """Each component is validated alone so cross-field checks cannot mask a leaking pattern.

    Both halves of this test carry real signal: the known-good value must be accepted by itself
    (otherwise the case proves nothing), and that same value with one appended newline must be
    rejected (this is what previously leaked, since Python's `$` also matches before a trailing
    newline).
    """
    build(good)                                                   # known-good is valid on its own
    with pytest.raises(ValidationError):
        build(good + "\n")                                        # the same value, one newline appended


def test_run_id_and_toolchain_key_reject_a_trailing_newline():
    rejects(with_(completed(), "run_id", "20260927T003000Z-modular-partial-refund\n"))
    rejects(with_(completed(), "toolchain", {"python\n": "3"}))
    assert re.fullmatch(mf.RUN_ID_PATTERN, "20260927T003000Z-modular-partial-refund")
    assert not re.search(mf.RUN_ID_PATTERN, "20260927T003000Z-modular-partial-refund\n")
    assert not re.search(mf.REF_PATTERN, "modular\n") and not re.search(mf.REL_PATH_PATTERN, "a/b\n")
