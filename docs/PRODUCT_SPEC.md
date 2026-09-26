# Product specification

## Product thesis

Developers evaluate a design mostly from present behavior, static structure, and expert opinion. Many architectural consequences appear only when the system must change. AI coding agents make it cheap enough to perform several bounded future changes as experiments before committing to a design.

FutureFork turns this into a developer workflow: **rehearse change, collect evidence, decide now**.

## Primary user

A developer or reviewer choosing between two internal implementations that provide the same observable behavior today, especially before merging an architectural refactor or foundational feature.

Secondary users are staff engineers reviewing architecture and teams planning near-term roadmap work.

## User job

> When two implementations both pass today's tests, help me understand how they respond to plausible future changes so I can make a better-informed decision without manually building every future myself.

## Input contract

Required:

- A Git repository with a reproducible setup and test command.
- Two clean candidate refs with equivalent current behavior.
- One to three bounded future scenarios.
- An evaluator-owned acceptance test pack for each scenario.
- Execution limits: wall time, edit scope, command allowlist, and maximum attempts.

Optional:

- Roadmap or architecture documents used only to propose scenarios.
- Protected architecture boundaries and public API paths.
- A human-approved present-day refactor to evaluate after the first comparison.

## Output contract

For every candidate × scenario run:

- Starting and ending commit/hash information.
- Exact scenario and acceptance-test hashes.
- Bob task/session reference.
- Final patch and changed-file inventory.
- Test and build results, including protected acceptance tests.
- Attempt/event history and failure classification.
- Observed boundary or public-interface changes.
- Duration and configured limits.
- An explicit status: `completed`, `tests_failed`, `budget_exhausted`, `invalid`, or `runner_error`.

For a comparison:

- A side-by-side evidence matrix.
- A plain-language Bob analysis whose every factual statement links to an artifact.
- Limitations and untested areas.
- Optionally, one minimal present-day refactor proposal and evidence from a rerun.

## Core experience

1. User selects the two candidates.
2. FutureFork verifies they are clean and pass today's common contract.
3. User selects or edits proposed future scenarios.
4. User approves execution limits and starts the rehearsal.
5. Bob works on isolated worktrees, one scenario at a time or in parallel.
6. FutureFork executes protected tests and records immutable artifacts.
7. User explores the evidence matrix and diffs.
8. Bob proposes a small present-day improvement.
9. User chooses whether to test that improvement; nothing is merged automatically.

## MVP functional requirements

- **FR1:** Validate two candidate refs and record their commit hashes.
- **FR2:** Verify the same current contract passes on both candidates before comparison.
- **FR3:** Parse versioned YAML scenarios with stable IDs and acceptance commands.
- **FR4:** Create isolated worktrees for each run.
- **FR5:** Generate a consistent Bob task packet for every candidate × scenario pair.
- **FR6:** Enforce time, command, and editable-path limits.
- **FR7:** Keep acceptance tests unavailable for editing and verify their hashes.
- **FR8:** Capture patches, commands, logs, events, test results, and provenance.
- **FR9:** Render the evidence without inventing a universal quality score.
- **FR10:** Allow one human-approved refactor and one evidence rerun.
- **FR11:** Export a static report suitable for the demo and repository.

## Non-functional requirements

- Local-first and synthetic-data-only for the hackathon demo.
- A failed or interrupted run must preserve enough state to diagnose it.
- Source candidates are read-only from the runner's perspective.
- Results must be reproducible from recorded refs, scenario, test pack, and commands, subject to Bob/model nondeterminism.
- The UI must distinguish observation, Bob interpretation, and human decision.

## Explicit non-goals

- Predicting which roadmap items will actually happen.
- Proving an architecture is maintainable or optimal.
- Replacing architecture review or user judgment.
- Comparing different AI models.
- General autonomous development across arbitrary repositories in the MVP.
- Automatically merging future implementations.
- Producing financial ROI claims without real measurement.

## Success criteria for the hackathon

The project is credible if a judge can see two candidates that pass today, inspect at least one real future implementation on each candidate, reproduce the protected test results, and understand one decision that the evidence changed.

The project is memorable if the judge can summarize it later as: “They actually made Bob maintain both designs in the future before deciding which one to merge.”

## Key risks

| Risk | Mitigation |
|---|---|
| Bob succeeds on one candidate by chance | Identical task packet, fixed limits, optional repeated run, disclose variance |
| Tests encode the desired winner | Freeze and hash tests before runs; add neutral and held-out scenarios |
| Diff size is mistaken for quality | Show multiple raw measures and qualitative evidence; no magic score |
| Demo is pre-scripted | Let judge choose a held-out scenario or inspect raw worktrees/artifacts |
| Future scenario is unrealistic | Human approval, provenance from roadmap, label it as a hypothesis |
| Agent edits evaluator | Protected test path and post-run hash verification |
| Long live execution | Use a precomputed signed run for the main video; reserve one small live action |

