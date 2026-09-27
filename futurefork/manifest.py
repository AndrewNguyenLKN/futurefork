"""Run manifest contract: one immutable record of a candidate x scenario run.

The Pydantic models are the single definition. `schemas/run-manifest.schema.json` is
generated from them (`python -m futurefork.manifest schema --write|--check`). JSON Schema
can express the field shapes; the cross-field invariants (outcome vs. test states, artifact
cross-references, limits) are enforced only by the models, so consumers must load manifests
with `load_manifest`, not with a schema validator alone.

Nothing here computes a quality score: measurements are raw observations.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from .scenario import SCENARIO_ID_PATTERN, Limits

SCHEMA_VERSION = 1
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "run-manifest.schema.json"
JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"

# --- identifiers and hashes -----------------------------------------------------------

def _anchored(pattern: str) -> str:
    """End-anchor that rejects a trailing newline. Python's `$` also matches before a final
    '\n', so 'modular\n' would pass a plain `^...$`; `(?!\n)` closes that and is harmless in
    the ECMAScript dialect used by JSON Schema consumers."""
    assert pattern.endswith("$")
    return pattern + r"(?!\n)"


_SEGMENT = r"(?!\.{1,2}(?:/|$))[A-Za-z0-9._-]+"
REL_PATH_PATTERN = _anchored(rf"^{_SEGMENT}(?:/{_SEGMENT})*$")
# A ref is a *name*. A 40/64-hex string is a commit id, never a valid ref here.
REF_PATTERN = _anchored(r"^(?![0-9a-f]{40}(?:[0-9a-f]{24})?$)(?![-/.])(?!.*(?:\.\.|//|\.lock(?:/|$)))[A-Za-z0-9._/-]{1,200}(?<![/.])$")
RUN_ID_PATTERN = _anchored(r"^\d{8}T\d{6}Z-[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")

Sha256 = Annotated[str, Field(pattern=_anchored(r"^[0-9a-f]{64}$"), description="Lowercase hex SHA-256.")]
GitOid = Annotated[str, Field(pattern=_anchored(r"^[0-9a-f]{40}$"), description="Full lowercase 40-hex Git object id.")]
RelPath = Annotated[
    str,
    Field(max_length=240, pattern=REL_PATH_PATTERN,
          description="Relative POSIX path inside the run directory; no '..', no absolute paths."),
]
Identifier = Annotated[str, Field(pattern=_anchored(SCENARIO_ID_PATTERN))]


class _Strict(BaseModel):
    # python-re: the path/ref patterns need lookaheads, which the default Rust engine lacks.
    model_config = ConfigDict(extra="forbid", frozen=True, regex_engine="python-re")


# --- enumerations ------------------------------------------------------------------------

class Outcome(StrEnum):
    """Canonical failure taxonomy (docs/ARCHITECTURE.md; decision D014)."""

    CANDIDATE_INVALID = "candidate_invalid"
    SETUP_FAILED = "setup_failed"
    BUDGET_EXHAUSTED = "budget_exhausted"
    REGRESSION_FAILED = "regression_failed"
    ACCEPTANCE_FAILED = "acceptance_failed"
    ORACLE_TAMPERED = "oracle_tampered"
    RUNNER_ERROR = "runner_error"
    COMPLETED = "completed"


class OutcomeClass(StrEnum):
    EXPERIMENTAL = "experimental"      # evidence about the candidate under this experiment
    INTEGRITY = "integrity"            # the experiment itself is compromised
    INFRASTRUCTURE = "infrastructure"  # says nothing about the candidate


OUTCOME_CLASS = {
    Outcome.COMPLETED: OutcomeClass.EXPERIMENTAL,
    Outcome.ACCEPTANCE_FAILED: OutcomeClass.EXPERIMENTAL,
    Outcome.REGRESSION_FAILED: OutcomeClass.EXPERIMENTAL,
    Outcome.BUDGET_EXHAUSTED: OutcomeClass.EXPERIMENTAL,
    Outcome.ORACLE_TAMPERED: OutcomeClass.INTEGRITY,
    Outcome.CANDIDATE_INVALID: OutcomeClass.INFRASTRUCTURE,
    Outcome.SETUP_FAILED: OutcomeClass.INFRASTRUCTURE,
    Outcome.RUNNER_ERROR: OutcomeClass.INFRASTRUCTURE,
}


def outcome_class(outcome: Outcome) -> OutcomeClass:
    return OUTCOME_CLASS[outcome]


class TestState(StrEnum):
    __test__ = False  # not a pytest class

    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"      # the tests could not be run or crashed (not a verdict on the candidate)
    NOT_RUN = "not_run"


class ArtifactKind(StrEnum):
    SCENARIO = "scenario"
    TASK_PACKET = "task_packet"
    PATCH = "patch"
    CHANGED_PATHS = "changed_paths"
    TEST_RESULTS = "test_results"
    MEASUREMENTS = "measurements"
    EVENTS = "events"
    STDOUT_LOG = "stdout_log"
    STDERR_LOG = "stderr_log"
    ARTIFACT_HASHES = "artifact_hashes"
    JUNIT_XML = "junit_xml"
    NOTES = "notes"
    OTHER = "other"


# --- components -----------------------------------------------------------------------------

class Candidate(_Strict):
    name: Identifier
    ref: str = Field(pattern=REF_PATTERN, description="Git ref name, e.g. 'modular'. Never a commit id.")
    starting_commit: GitOid


class ScenarioRef(_Strict):
    id: Identifier
    sha256: Sha256 = Field(description="SHA-256 of the exact scenario YAML bytes.")


class Evaluator(_Strict):
    test_pack_sha256: Sha256 = Field(description="Frozen protected-pack hash from PACKS.json.")
    observed_sha256_after_run: Sha256 | None = Field(
        default=None, description="Pack hash re-computed after evaluation; None if it was not evaluated."
    )


class Agent(_Strict):
    provider: Literal["IBM Bob"]
    task_id: Annotated[str, Field(pattern=_anchored(r"^[A-Za-z0-9._-]{8,128}$"))] | None = None
    human_triggered: bool


class TestRun(_Strict):
    __test__ = False  # not a pytest class

    state: TestState
    command: list[Annotated[str, Field(min_length=1)]] | None = None
    returncode: int | None = None
    passed: int | None = Field(default=None, ge=0)
    failed: int | None = Field(default=None, ge=0)
    errors: int | None = Field(default=None, ge=0)
    skipped: int | None = Field(default=None, ge=0)
    results_artifact: RelPath | None = None

    @property
    def has_counts(self) -> bool:
        return None not in (self.passed, self.failed, self.errors, self.skipped)

    @model_validator(mode="after")
    def _state_matches_evidence(self) -> "TestRun":
        counts = [self.passed, self.failed, self.errors, self.skipped]
        if self.state is TestState.NOT_RUN:
            if any(v is not None for v in (*counts, self.returncode, self.results_artifact)):
                raise ValueError("a not_run test cannot carry counts, a returncode, or results")
            return self
        if any(v is not None for v in counts) and not self.has_counts:
            raise ValueError("test counts must be given together (passed, failed, errors, skipped)")
        if self.state in (TestState.FAILED, TestState.ERROR) and self.returncode == 0:
            raise ValueError(f"state {self.state.value} conflicts with returncode 0")
        if self.state is TestState.PASSED:
            if self.returncode not in (None, 0):
                raise ValueError("state passed conflicts with a non-zero returncode")
            if self.has_counts and (self.failed or self.errors or not self.passed):
                raise ValueError("state passed requires passed >= 1 and no failed/errored tests")
        if self.state is TestState.FAILED and self.has_counts and not self.failed:
            raise ValueError("state failed requires failed >= 1 when counts are given")
        if self.state is TestState.ERROR and self.has_counts and self.failed and not self.errors:
            raise ValueError("state error conflicts with counts that show only failed tests")
        return self


class Tests(_Strict):
    __test__ = False  # not a pytest class

    regression: TestRun
    protected: TestRun


class Event(_Strict):
    description: str = Field(min_length=1, max_length=500)
    provenance: Literal["observed", "reported"] = Field(
        description="observed: seen by the runner/evaluator; reported: an operator statement not verified."
    )
    evidence: RelPath | None = None


class Measurements(_Strict):
    """Raw observations only. There is deliberately no score field."""

    attempts: int | None = Field(default=None, ge=0)
    duration_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    output_bytes: int | None = Field(default=None, ge=0)
    changed_files: int | None = Field(default=None, ge=0)
    lines_added: int | None = Field(default=None, ge=0)
    lines_deleted: int | None = Field(default=None, ge=0)
    human_interventions: list[Event] = Field(default_factory=list)
    boundary_violations: list[Event] = Field(default_factory=list)


class Ending(_Strict):
    commit: GitOid | None = None
    tree: GitOid | None = None
    diff_artifact: RelPath | None = None


class Artifact(_Strict):
    path: RelPath
    kind: ArtifactKind
    sha256: Sha256
    size_bytes: int = Field(ge=0)

    @field_validator("path")
    @classmethod
    def _not_the_manifest(cls, v: str) -> str:
        if v == "manifest.json":
            raise ValueError("manifest.json cannot list itself (its hash cannot be self-referential)")
        return v


# --- manifest ---------------------------------------------------------------------------------

_INFRA_NEEDS_DETAIL = {Outcome.CANDIDATE_INVALID, Outcome.SETUP_FAILED, Outcome.RUNNER_ERROR, Outcome.ORACLE_TAMPERED}
_NO_AGENT_YET = {Outcome.CANDIDATE_INVALID, Outcome.SETUP_FAILED}
_RESULT_KINDS = {ArtifactKind.TEST_RESULTS, ArtifactKind.JUNIT_XML}
# The evidence bundle from docs/ARCHITECTURE.md (manifest.json itself is not listed). A completed
# run must be traceable from files, not from self-reported counts.
_COMPLETED_REQUIRED_KINDS = (
    ArtifactKind.SCENARIO, ArtifactKind.TASK_PACKET, ArtifactKind.PATCH, ArtifactKind.CHANGED_PATHS,
    ArtifactKind.TEST_RESULTS, ArtifactKind.MEASUREMENTS, ArtifactKind.EVENTS,
    ArtifactKind.STDOUT_LOG, ArtifactKind.STDERR_LOG, ArtifactKind.ARTIFACT_HASHES,
)
_NEEDS_ENDING_DIFF = {Outcome.COMPLETED, Outcome.REGRESSION_FAILED, Outcome.ACCEPTANCE_FAILED}
_NEEDS_FINISHED = {
    Outcome.COMPLETED, Outcome.REGRESSION_FAILED, Outcome.ACCEPTANCE_FAILED,
    Outcome.BUDGET_EXHAUSTED, Outcome.ORACLE_TAMPERED,
}


class RunManifest(_Strict):
    schema_version: Literal[1]
    run_id: str = Field(pattern=RUN_ID_PATTERN, description="<UTC start YYYYMMDDTHHMMSSZ>-<candidate>-<scenario>")
    candidate: Candidate
    scenario: ScenarioRef
    evaluator: Evaluator
    agent: Agent
    limits: Limits
    toolchain: dict[Annotated[str, Field(pattern=_anchored(r"^[a-z][a-z0-9_.-]{0,40}$"))], Annotated[str, Field(max_length=200)]] = Field(
        default_factory=dict, description="Allowlisted tool versions only; never environment dumps."
    )
    started_at: AwareDatetime
    finished_at: AwareDatetime | None = None
    outcome: Outcome
    outcome_detail: str | None = Field(default=None, min_length=1, max_length=2000)
    tests: Tests
    measurements: Measurements
    ending: Ending | None = None
    artifacts: list[Artifact]

    @field_validator("schema_version", mode="before")
    @classmethod
    def _version_is_an_integer_not_a_bool(cls, v: object) -> object:
        if isinstance(v, bool):
            raise ValueError("schema_version must be the integer 1, not a boolean")
        return v

    # -- timestamps: UTC, whole seconds, deterministic text --------------------------------------

    @field_validator("started_at", "finished_at")
    @classmethod
    def _utc_whole_seconds(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return v
        if v.utcoffset() != timedelta(0):
            raise ValueError("timestamps must be UTC")
        if v.microsecond:
            raise ValueError("timestamps have whole-second precision")
        return v

    @field_serializer("started_at", "finished_at")
    def _ser_time(self, v: datetime | None) -> str | None:
        return None if v is None else v.strftime("%Y-%m-%dT%H:%M:%SZ")

    # -- cross-field invariants --------------------------------------------------------------------

    @model_validator(mode="after")
    def _identity_and_time(self) -> "RunManifest":
        expected_suffix = f"-{self.candidate.name}-{self.scenario.id}"
        if not self.run_id.endswith(expected_suffix):
            raise ValueError(f"run_id must end with {expected_suffix!r}")
        if self.run_id[: -len(expected_suffix)] != self.started_at.strftime("%Y%m%dT%H%M%SZ"):
            raise ValueError("run_id timestamp must equal started_at")
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("finished_at precedes started_at")
        if self.finished_at is None and self.outcome in _NEEDS_FINISHED:
            raise ValueError(f"outcome {self.outcome.value} requires finished_at")
        return self

    @model_validator(mode="after")
    def _artifacts_are_safe_and_consistent(self) -> "RunManifest":
        seen: dict[str, str] = {}
        for artifact in self.artifacts:
            key = artifact.path.casefold()  # case-insensitive filesystems must not collide
            if key in seen:
                raise ValueError(f"duplicate artifact path: {artifact.path!r} vs {seen[key]!r}")
            seen[key] = artifact.path
        for a in seen:
            parts = a.split("/")
            for i in range(1, len(parts)):
                if "/".join(parts[:i]) in seen:
                    raise ValueError(f"artifact {seen['/'.join(parts[:i])]!r} is both a file and a directory")
        by_path = {a.path: a for a in self.artifacts}

        def require(path: str | None, kind: ArtifactKind | None, what: str) -> None:
            if path is None:
                return
            if path not in by_path:
                raise ValueError(f"{what} {path!r} is not listed in artifacts")
            if kind is not None and by_path[path].kind is not kind:
                raise ValueError(f"{what} {path!r} must have kind {kind.value}")

        require(self.ending.diff_artifact if self.ending else None, ArtifactKind.PATCH, "ending.diff_artifact")
        for name, run in (("regression", self.tests.regression), ("protected", self.tests.protected)):
            if run.results_artifact is not None:
                require(run.results_artifact, None, f"tests.{name}.results_artifact")
                if by_path[run.results_artifact].kind not in _RESULT_KINDS:
                    raise ValueError(
                        f"tests.{name}.results_artifact {run.results_artifact!r} must have kind test_results or junit_xml"
                    )
        for events in (self.measurements.human_interventions, self.measurements.boundary_violations):
            for event in events:
                require(event.evidence, None, "event evidence")
        for artifact in self.artifacts:
            if artifact.kind is ArtifactKind.SCENARIO and artifact.sha256 != self.scenario.sha256:
                raise ValueError("the scenario artifact's sha256 must equal scenario.sha256")
        return self

    @model_validator(mode="after")
    def _outcome_invariants(self) -> "RunManifest":
        o, reg, prot = self.outcome, self.tests.regression.state, self.tests.protected.state
        m, lim = self.measurements, self.limits
        pack, observed = self.evaluator.test_pack_sha256, self.evaluator.observed_sha256_after_run

        if outcome_class(o) is OutcomeClass.INFRASTRUCTURE and TestState.FAILED in (reg, prot):
            raise ValueError("an infrastructure outcome cannot record a failed test: that would read as a candidate failure")
        if o in _INFRA_NEEDS_DETAIL and not self.outcome_detail:
            raise ValueError(f"outcome {o.value} requires outcome_detail")
        if o is Outcome.COMPLETED and self.outcome_detail:
            raise ValueError("a completed run has no outcome_detail")
        if o in _NO_AGENT_YET:
            if self.agent.task_id is not None or m.attempts not in (None, 0):
                raise ValueError(f"{o.value} happens before any agent work: no task_id, attempts must be 0")
            if reg is not TestState.NOT_RUN or prot is not TestState.NOT_RUN:
                raise ValueError(f"{o.value} requires both test runs to be not_run")

        if o is Outcome.COMPLETED:
            if reg is not TestState.PASSED or prot is not TestState.PASSED:
                raise ValueError("completed requires regression and protected to be passed")
            if observed != pack:
                raise ValueError("completed requires the observed pack hash to equal the frozen hash")
            if self.agent.task_id is None:
                raise ValueError("completed requires agent.task_id")
            if not (self.tests.regression.has_counts and self.tests.protected.has_counts):
                raise ValueError("completed requires test counts for both runs")
            for name, run in (("regression", self.tests.regression), ("protected", self.tests.protected)):
                if run.returncode != 0 or not run.command:
                    raise ValueError(f"completed requires tests.{name} to record its command and returncode 0")
                if run.results_artifact is None:
                    raise ValueError(f"completed requires tests.{name}.results_artifact")
            present = {a.kind for a in self.artifacts}
            missing = [k.value for k in _COMPLETED_REQUIRED_KINDS if k not in present]
            if missing:
                raise ValueError(f"completed requires the evidence bundle; missing artifact kinds: {missing}")
            if m.attempts is None or m.duration_seconds is None:
                raise ValueError("completed requires measurements.attempts and duration_seconds")
            if not 1 <= m.attempts <= lim.max_attempts:
                raise ValueError("completed requires 1 <= attempts <= limits.max_attempts")
            if m.duration_seconds > lim.wall_seconds:
                raise ValueError("completed requires duration within limits.wall_seconds")
            if m.output_bytes is not None and m.output_bytes > lim.max_output_bytes:
                raise ValueError("completed requires output within limits.max_output_bytes")
        if o in _NEEDS_ENDING_DIFF:
            if self.ending is None or self.ending.diff_artifact is None or not (self.ending.commit or self.ending.tree):
                raise ValueError(f"{o.value} requires ending.diff_artifact and an ending commit or tree")

        if o is Outcome.REGRESSION_FAILED and reg is not TestState.FAILED:
            raise ValueError("regression_failed requires tests.regression.state == failed")
        if o is Outcome.ACCEPTANCE_FAILED and not (reg is TestState.PASSED and prot is TestState.FAILED):
            raise ValueError("acceptance_failed requires regression passed and protected failed")
        if o is Outcome.ORACLE_TAMPERED:
            if prot is TestState.PASSED:
                raise ValueError("oracle_tampered cannot record protected as passed")
            if observed is None or observed == pack:
                raise ValueError("oracle_tampered requires an observed pack hash that differs from the frozen hash")
        elif observed is not None and observed != pack and o is not Outcome.RUNNER_ERROR:
            raise ValueError("an observed pack hash that differs from the frozen one can only be recorded as oracle_tampered")
        if o is Outcome.BUDGET_EXHAUSTED:
            if reg is TestState.PASSED and prot is TestState.PASSED:
                raise ValueError("budget_exhausted cannot record both test runs as passed")
            exhausted = (
                (m.attempts is not None and m.attempts >= lim.max_attempts)
                or (m.duration_seconds is not None and m.duration_seconds >= lim.wall_seconds)
                or (m.output_bytes is not None and m.output_bytes >= lim.max_output_bytes)
            )
            if not exhausted:
                raise ValueError("budget_exhausted requires a measurement that reached its limit")
        return self


# --- canonical serialization ---------------------------------------------------------------------

def _to_data(manifest: RunManifest) -> dict:
    return manifest.model_dump(mode="json")


def canonical_json(manifest: RunManifest) -> str:
    """Compact, key-sorted, ASCII JSON. The bytes that are hashed."""
    return json.dumps(_to_data(manifest), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def dump_manifest(manifest: RunManifest) -> str:
    """Human-readable but still deterministic text for manifest.json (ends with a newline)."""
    return json.dumps(_to_data(manifest), sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n"


def manifest_sha256(manifest: RunManifest) -> str:
    import hashlib

    return hashlib.sha256(canonical_json(manifest).encode("ascii")).hexdigest()


def _reject_duplicates(pairs: list[tuple[str, object]]) -> dict:
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        dupes = sorted({k for k in keys if keys.count(k) > 1})
        raise ValueError(f"duplicate JSON object keys: {dupes}")
    return dict(pairs)


def _refuse_constant(name: str):
    raise ValueError(f"non-finite number {name} is not allowed")


def loads_manifest(text: str) -> RunManifest:
    """Strict load: duplicate keys, NaN/Infinity, unknown fields, and type coercion are all rejected."""
    json.loads(text, object_pairs_hook=_reject_duplicates, parse_constant=_refuse_constant)
    return RunManifest.model_validate_json(text, strict=True)


def load_manifest(path: Path | str) -> RunManifest:
    return loads_manifest(Path(path).read_text(encoding="utf-8"))


def write_manifest(manifest: RunManifest, path: Path | str) -> None:
    """Write exclusively: an existing manifest is immutable and is never overwritten."""
    with open(path, "x", encoding="utf-8", newline="\n") as handle:
        handle.write(dump_manifest(manifest))


# --- JSON Schema -----------------------------------------------------------------------------------

def manifest_json_schema() -> dict:
    schema = RunManifest.model_json_schema(mode="validation")
    return {"$schema": JSON_SCHEMA_DIALECT, **schema}


def schema_text() -> str:
    return json.dumps(manifest_json_schema(), sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m futurefork.manifest")
    sub = ap.add_subparsers(dest="cmd", required=True)
    schema = sub.add_parser("schema", help="write or check schemas/run-manifest.schema.json")
    group = schema.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    text = schema_text()
    if args.write:
        SCHEMA_PATH.parent.mkdir(exist_ok=True)
        SCHEMA_PATH.write_text(text, encoding="utf-8")
        print(f"wrote {SCHEMA_PATH}")
        return 0
    if not SCHEMA_PATH.exists() or SCHEMA_PATH.read_text(encoding="utf-8") != text:
        print("schemas/run-manifest.schema.json is out of date with the model", file=sys.stderr)
        return 1
    print("run-manifest schema matches the model")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
