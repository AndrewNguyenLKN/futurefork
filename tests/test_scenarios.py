"""P0.1: the three demo scenario contracts are valid, frozen, and fair."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from futurefork.scenario import Scenario, load_scenario, scenario_sha256

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "scenarios" / "demo"
EXPECTED_IDS = ["partial-refund", "organization-pricing", "ordered-discounts"]
DEMO_STORY_HEADINGS = {
    "partial-refund": "### F1",
    "organization-pricing": "### F2",
    "ordered-discounts": "### F3",
}


def _raw(scenario_id: str) -> dict:
    return yaml.safe_load((DEMO / f"{scenario_id}.yaml").read_text())


@pytest.fixture(scope="module")
def scenarios() -> dict[str, Scenario]:
    return {i: load_scenario(DEMO / f"{i}.yaml") for i in EXPECTED_IDS}


def test_exactly_the_three_demo_scenarios_exist():
    assert sorted(p.stem for p in DEMO.glob("*.yaml")) == sorted(EXPECTED_IDS)


def test_ids_match_filenames_and_are_labelled_hypotheses(scenarios):
    for sid, s in scenarios.items():
        assert s.id == sid
        assert s.label == "hypothesis"
        assert s.schema_version == 1


@pytest.mark.parametrize("sid", EXPECTED_IDS)
def test_requirement_matches_demo_story_verbatim(sid, scenarios):
    story = (ROOT / "docs" / "DEMO_STORY.md").read_text()
    section = story.split(DEMO_STORY_HEADINGS[sid], 1)[1].split("\n## ", 1)[0].split("\n### ", 1)[0]
    quoted = " ".join(
        line[1:].strip() for line in section.splitlines() if line.startswith(">")
    )
    assert quoted, "no blockquote requirement found in DEMO_STORY.md"
    assert " ".join(scenarios[sid].requirement.split()) == quoted


def test_fair_comparison_fields_identical_across_scenarios(scenarios):
    """Same limits, commands, allowlist, and paths for every scenario."""
    first = scenarios[EXPECTED_IDS[0]]
    for s in scenarios.values():
        assert s.limits == first.limits
        assert s.setup_command == first.setup_command
        assert s.dev_test_command == first.dev_test_command
        assert s.command_allowlist == first.command_allowlist
        assert s.editable_paths == first.editable_paths
        assert s.protected_paths == first.protected_paths


def test_fixed_budgets(scenarios):
    for s in scenarios.values():
        assert s.limits.wall_seconds == 600
        assert s.limits.max_attempts == 4


def test_protected_tests_are_distinct_and_outside_editable_area(scenarios):
    mounts = [s.protected_tests.mount for s in scenarios.values()]
    sources = [s.protected_tests.source for s in scenarios.values()]
    assert len(set(mounts)) == len(set(sources)) == 3
    for s in scenarios.values():
        assert s.protected_tests.source.startswith("scenarios/demo/protected-tests/")
        assert s.protected_test_command[-1] == s.protected_tests.mount


def test_commands_are_argv_arrays(scenarios):
    for s in scenarios.values():
        for cmd in [s.dev_test_command, s.protected_test_command, *s.command_allowlist]:
            assert all(isinstance(a, str) and a for a in cmd)
        # Every scenario command must be permitted by the allowlist.
        for cmd in (s.dev_test_command, s.protected_test_command):
            assert any(cmd[: len(a)] == a for a in s.command_allowlist)


def test_public_packet_does_not_reference_the_oracle(scenarios):
    for s in scenarios.values():
        public = s.public_interface.model_dump_json() + " ".join(
            s.public_acceptance_criteria
        ) + s.requirement
        assert "protected" not in public.lower()
        assert ".futurefork-evaluator" not in public
        assert not re.search(r"\bpredict(s|ion|ions)?\b", public.lower())


def test_every_scenario_states_its_interface(scenarios):
    for s in scenarios.values():
        assert s.public_interface.endpoints
        assert len(s.public_interface.rules) >= 4


def test_frozen_hashes_match_files():
    lines = (DEMO / "FROZEN.sha256").read_text().splitlines()
    expected = {f"{i}.yaml": scenario_sha256(DEMO / f"{i}.yaml") for i in EXPECTED_IDS}
    recorded = {name: h for h, name in (re.split(r"\s+", l, maxsplit=1) for l in lines)}
    assert recorded == expected


def test_freeze_script_check_passes():
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "freeze_scenarios.py"), "check"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr


# --- tamper / invalid-input cases -------------------------------------------------

def _mutate(sid: str, fn) -> dict:
    raw = _raw(sid)
    fn(raw)
    return raw


def test_rejects_editable_path_overlapping_protected_mount():
    raw = _mutate("partial-refund", lambda r: r["editable_paths"].append(".futurefork-evaluator/**"))
    with pytest.raises(ValidationError, match="overlaps protected mount"):
        Scenario.model_validate(raw)


def test_rejects_protected_paths_not_covering_mount():
    raw = _mutate("partial-refund", lambda r: r.update(protected_paths=["other/**"]))
    with pytest.raises(ValidationError, match="must cover"):
        Scenario.model_validate(raw)


def test_rejects_protected_source_outside_evaluator_area():
    raw = _mutate("partial-refund", lambda r: r["protected_tests"].update(source="src/tests"))
    with pytest.raises(ValidationError):
        Scenario.model_validate(raw)


def test_rejects_protected_test_command_targeting_other_path():
    raw = _mutate("partial-refund", lambda r: r.update(protected_test_command=["pytest", "tests"]))
    with pytest.raises(ValidationError, match="must target"):
        Scenario.model_validate(raw)


def test_rejects_shell_string_command():
    raw = _mutate("partial-refund", lambda r: r.update(dev_test_command="pytest -q"))
    with pytest.raises(ValidationError):
        Scenario.model_validate(raw)


def test_rejects_unknown_key_missing_label_and_bad_version():
    with pytest.raises(ValidationError):
        Scenario.model_validate(_mutate("partial-refund", lambda r: r.update(expected_winner="modular")))
    with pytest.raises(ValidationError):
        Scenario.model_validate(_mutate("partial-refund", lambda r: r.pop("label")))
    with pytest.raises(ValidationError):
        Scenario.model_validate(_mutate("partial-refund", lambda r: r.update(schema_version=2)))


def test_rejects_non_positive_limits():
    raw = _mutate("partial-refund", lambda r: r["limits"].update(wall_seconds=0))
    with pytest.raises(ValidationError):
        Scenario.model_validate(raw)


def test_frozen_check_detects_edit(tmp_path):
    """A changed byte changes the recorded hash, so an edit cannot go unnoticed."""
    original = DEMO / "partial-refund.yaml"
    copy = tmp_path / "partial-refund.yaml"
    copy.write_bytes(original.read_bytes() + b"# edit\n")
    assert scenario_sha256(copy) != scenario_sha256(original)
