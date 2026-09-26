"""Scenario contract: versioned YAML definitions for frozen future hypotheses."""

from __future__ import annotations

import hashlib
from fnmatch import fnmatch
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = 1
SCENARIO_ID_PATTERN = r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Limits(_Strict):
    wall_seconds: int = Field(gt=0)
    max_attempts: int = Field(gt=0)
    max_output_bytes: int = Field(gt=0)


class Endpoint(_Strict):
    method: Literal["GET", "POST"]
    path: str
    summary: str
    request: dict = Field(default_factory=dict)
    response: dict = Field(default_factory=dict)
    errors: dict[int, str] = Field(default_factory=dict)


class PublicInterface(_Strict):
    """Black-box HTTP contract that protected tests exercise. Visible to Bob."""

    endpoints: list[Endpoint] = Field(min_length=1)
    rules: list[str] = Field(min_length=1)


class ProtectedTests(_Strict):
    # Evaluator-owned source directory, relative to the repository root.
    source: str
    # Where the runner mounts it inside a worktree after editing stops.
    mount: str

    @field_validator("source")
    @classmethod
    def _source_under_protected_tests(cls, v: str) -> str:
        if not v.startswith("scenarios/demo/protected-tests/") or ".." in Path(v).parts:
            raise ValueError("source must live under scenarios/demo/protected-tests/")
        return v


class Scenario(_Strict):
    schema_version: Literal[1]
    id: str = Field(pattern=SCENARIO_ID_PATTERN)
    title: str
    label: Literal["hypothesis"]
    requirement: str
    public_acceptance_criteria: list[str] = Field(min_length=1)
    public_interface: PublicInterface
    setup_command: list[str]  # argv; empty list means no setup step
    dev_test_command: list[str] = Field(min_length=1)
    protected_test_command: list[str] = Field(min_length=1)
    protected_tests: ProtectedTests
    editable_paths: list[str] = Field(min_length=1)
    protected_paths: list[str] = Field(min_length=1)
    command_allowlist: list[list[str]] = Field(min_length=1)
    limits: Limits
    tags: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def _oracle_is_outside_editable_area(self) -> "Scenario":
        mount = self.protected_tests.mount.rstrip("/")
        probe = f"{mount}/test_probe.py"
        if not any(fnmatch(probe, p) for p in self.protected_paths):
            raise ValueError("protected_paths must cover protected_tests.mount")
        for e in self.editable_paths:
            if fnmatch(probe, e):
                raise ValueError(f"editable path {e!r} overlaps protected mount")
        if mount not in self.protected_test_command:
            raise ValueError("protected_test_command must target protected_tests.mount")
        return self


def load_scenario(path: Path | str) -> Scenario:
    return Scenario.model_validate(yaml.safe_load(Path(path).read_text()))


def scenario_sha256(path: Path | str) -> str:
    """Hash of the exact YAML bytes; this is the value recorded in run manifests."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
