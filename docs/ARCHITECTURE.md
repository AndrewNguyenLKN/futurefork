# Technical architecture

## System shape

```text
Bob IDE
  └─ FutureFork Skill
       ├─ reads repo + scenario packet
       ├─ reasons about implementation
       └─ calls local FutureFork MCP tools
             │
             ▼
FutureFork Orchestrator API / CLI
  ├─ candidate validator
  ├─ scenario registry
  ├─ worktree manager
  ├─ run controller
  ├─ protected test executor
  ├─ evidence collector
  └─ report builder
             │
             ├─ isolated Git worktrees
             ├─ evaluator-owned tests
             └─ immutable artifact bundles
             │
             ▼
React evidence dashboard / static HTML export
```

## Suggested repository layout

```text
apps/
  api/                       FastAPI endpoints and orchestration
  web/                       React/Vite evidence dashboard
futurefork/
  cli.py
  models.py                  Pydantic run/scenario/artifact models
  candidates.py
  worktrees.py
  runner.py
  evidence.py
  compare.py
  report.py
mcp/
  server.py                  Bob-facing tools
scenarios/
  demo/
    partial-refund.yaml
    organization-pricing.yaml
    ordered-discounts.yaml
    protected-tests/         inserted/mounted by evaluator
examples/
  pocketcart/
artifacts/
  runs/<run-id>/
.bob/skills/future-fork/
  SKILL.md
bob_sessions/
tests/
```

## Execution model

### Phase 1: validate candidates

1. Resolve candidate refs to immutable commit hashes.
2. Require a clean source repository.
3. Create validation worktrees.
4. Run the common current test suite against both candidates.
5. Stop the comparison if either fails or observable current behavior differs.

### Phase 2: prepare experiments

For every candidate × scenario pair:

1. Create a uniquely named detached worktree.
2. Copy the public scenario packet into the worktree.
3. Do not expose protected acceptance tests yet.
4. Record toolchain and dependency lock hashes.
5. Generate a task packet with identical instructions and limits.

### Phase 3: Bob implementation

Bob reads the candidate and scenario, makes changes, adds its own tests if useful, and runs the allowed development commands. The orchestration layer records task identity and events. Bob must not see the protected acceptance implementation.

For the hackathon MVP, a human may start or approve Bob tasks from the IDE. Do not pretend that an unavailable Bob API exists. The run manifest must distinguish automated steps from human-triggered steps.

### Phase 4: independent evaluation

1. Stop editing.
2. Capture the patch and changed-path inventory.
3. Inject or mount evaluator-owned acceptance tests.
4. Verify test hashes against the frozen scenario pack.
5. Run current regression tests and scenario acceptance tests.
6. Collect structured results and classify the run.
7. Make the artifact directory read-only where practical.

### Phase 5: compare and explain

The deterministic comparator creates the evidence matrix. Bob may produce a narrative interpretation, but each factual statement must reference manifest fields or artifacts. The UI visually separates:

- **Observed:** produced by Git, test runner, or run controller.
- **Interpreted:** Bob's explanation of observations.
- **Decided:** human selection or approval.

## Scenario schema

Minimum YAML shape (see `scenarios/demo/` and `futurefork/scenario.py`, which validates it; decisions D009 and D010):

```yaml
schema_version: 1
id: partial-refund
title: Partial refund allocation
label: hypothesis            # required; scenarios are hypotheses, not predictions
requirement: |
  Refund selected order items while preserving pricing invariants.
public_acceptance_criteria:
  - Existing full refunds remain compatible.
public_interface:            # black-box contract the protected tests call; visible to Bob
  endpoints: [{method: POST, path: "/orders/{order_id}/refunds", summary: "...", errors: {404: order_not_found}}]
  rules: ["exact arithmetic and error rules"]
setup_command: []            # argv array; empty means no setup step
dev_test_command: [python, -m, pytest, -q]
protected_test_command: [python, -m, pytest, -q, .futurefork-evaluator/partial_refund]
protected_tests:
  source: scenarios/demo/protected-tests/partial-refund   # evaluator-owned, outside candidates
  mount: .futurefork-evaluator/partial_refund             # where the runner mounts it after editing
editable_paths: ["src/**", "tests/**"]
protected_paths: [".futurefork-evaluator/**"]
command_allowlist: [[python, -m, pytest], [git, status], [git, diff]]
limits: {wall_seconds: 600, max_attempts: 4, max_output_bytes: 1000000}
tags: [pricing, persistence, refund]
```

Use explicit commands rather than shell fragments. The runner should invoke argument arrays where possible.

## Run manifest

Minimum fields:

```json
{
  "schema_version": 1,
  "run_id": "20260926T120000Z-coupled-partial-refund",
  "candidate": {"name": "coupled", "ref": "...", "commit": "..."},
  "scenario": {"id": "partial-refund", "sha256": "..."},
  "evaluator": {"test_pack_sha256": "..."},
  "agent": {"provider": "IBM Bob", "task_id": "...", "human_triggered": true},
  "limits": {"wall_seconds": 600, "max_attempts": 4},
  "outcome": "completed",
  "tests": {"regression": "passed", "protected": "passed"},
  "measurements": {},
  "artifacts": []
}
```

## Artifact bundle

Every run directory should contain:

```text
manifest.json
scenario.yaml
task-packet.md
patch.diff
changed-paths.json
test-results.json
measurements.json
events.jsonl
stdout.log
stderr.log
artifact-hashes.json
```

Do not store secrets, tokens, user data, or full environment dumps. Record only allowlisted tool versions and variables.

## Evidence measurements

Use raw observations, not a universal score:

- Acceptance outcome and regression outcome.
- Number of attempts and failure categories.
- Changed files and changed logical modules.
- Added/deleted lines as descriptive context only.
- Public API/interface files changed.
- Protected architecture-boundary violations.
- Test files added or changed by Bob.
- Overlap of touched files across separate futures, highlighting recurring hotspots.
- Wall time and agent interaction count, labeled as noisy.
- Human interventions, if any.

## Isolation and safety

- Candidate source refs are never checked out for editing.
- Each run gets a dedicated worktree and process group.
- Allowlist commands and paths; deny network by default for the seed demo.
- Use synthetic fixtures only.
- Set wall time, disk, and output limits.
- Terminate descendant processes on timeout.
- Preserve a failed run before cleanup.
- Do not use destructive Git commands on the source repository.
- Worktree cleanup must target an exact recorded path, never a broad glob.

## Bob MCP surface

Keep the MVP small:

- `ff_validate_candidates(base_ref, candidate_ref)`
- `ff_list_scenarios()`
- `ff_prepare_run(candidate_ref, scenario_id)`
- `ff_record_agent_checkpoint(run_id, summary)`
- `ff_finalize_editing(run_id)`
- `ff_evaluate_run(run_id)`
- `ff_compare_runs(run_ids)`
- `ff_get_artifact(run_id, artifact_name)`

The MCP server manages experiments and evidence. It should not impersonate Bob or silently generate code outside Bob IDE.

## UI screens

1. **Setup:** candidate refs, current contract status, and scenario selection.
2. **Run board:** one card per candidate × scenario with honest live state.
3. **Evidence matrix:** rows are scenarios, columns are candidates.
4. **Run detail:** diff, tests, events, measurements, and provenance.
5. **Refactor loop:** Bob recommendation, human approval, and rerun comparison.

## Failure taxonomy

- `candidate_invalid`: dirty/unresolvable ref or current contract failure.
- `setup_failed`: dependencies/build environment failed before Bob work.
- `budget_exhausted`: time or attempts ended without a valid solution.
- `regression_failed`: existing behavior broke.
- `acceptance_failed`: future requirement not satisfied.
- `oracle_tampered`: protected test or evaluator changed.
- `runner_error`: FutureFork infrastructure failed; do not count this against the candidate.
- `completed`: protected and regression tests passed within limits.

