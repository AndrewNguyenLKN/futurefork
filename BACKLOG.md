# FutureFork backlog

Work top to bottom. P0 is required for a credible submission; P1 improves the story; P2 is optional. Do not start a P1 while an end-to-end P0 path is broken.

## Do immediately

- [x] **P0.1 — Freeze the demo contract.** Create `scenarios/demo/` with three YAML scenario definitions, acceptance criteria, fixed budgets, and protected test paths matching `docs/DEMO_STORY.md`.
  - Status (2026-09-26): done and validated by `tests/test_scenarios.py`; YAML hashes frozen in `scenarios/demo/FROZEN.sha256`. Protected test packs are authored, baseline-verified, and hash-frozen (see `docs/PROTECTED_TESTS.md`); satisfiability is unproven until P0.3 runs a real implementation against them.
- [x] **P0.2 — Build the seed checkout application.** Create one small, deterministic application with `coupled` and `modular` Git refs. Both must expose identical behavior and pass identical current tests before any future scenario is applied.
  - Status (2026-09-26): complete. Refs `coupled` (`11f9d4e8559ec56fc818b9b9e72c2150e9560931`) and `modular` (`f9e3ecda1e4a8452678578226b2553a6ebddf536`) are local parentless commits made by `scripts/create_candidate_refs.sh` from baseline commit `0d8b6c2`; each tree is identical to its directory on `main`. `check_equivalence.py --refs .` passed (47 = 47 tests, one identical transcript hash across both candidates and both transports). Protected test packs are authored, baseline-verified, and hash-frozen (see `docs/PROTECTED_TESTS.md`); satisfiability is unproven until P0.3 runs a real implementation against them. Nothing has been pushed. Details: `examples/pocketcart/README.md`.
- [ ] **P0.3 — Prove one future manually in Bob.** In Bob IDE, implement `partial-refund` on one candidate, run its protected tests, and capture the task session summary in `bob_sessions/`. This validates the contest workflow before automation.
- [ ] **P0.4 — Define the run manifest.** Implement JSON Schema/Pydantic models for candidate, scenario, limits, Bob task ID, commit hashes, commands, outcomes, measurements, and artifact hashes.
- [ ] **P0.5 — Implement isolated Git execution.** Create and dispose one worktree per run without mutating either source ref. Detect dirty refs, naming collisions, timeouts, and cleanup failures safely.
- [ ] **P0.6 — Implement the runner CLI.** `futurefork run --candidate <ref> --scenario <yaml>` must produce `manifest.json`, `patch.diff`, `test-results.json`, `events.jsonl`, and logs under a new immutable run directory.
- [ ] **P0.7 — Protect the oracle.** Mount or copy evaluator-owned acceptance tests after Bob finishes editing; hash them before and after execution and fail closed if they change.
- [ ] **P0.8 — Complete the 2 × 3 evidence matrix.** Run both candidates against all three scenarios under identical limits. Record failures honestly; do not hand-correct only one side.
- [ ] **P0.9 — Build the comparison view.** Show scenario outcome, diff, files/modules touched, protected-test results, regressions, retries, boundary violations, duration, and artifact links. Avoid a single opaque score.
- [ ] **P0.10 — Close the learning loop.** Ask Bob to propose one small present-day refactor for the weaker candidate, approve it explicitly, rerun one scenario, and show before/after evidence.

## Submission-critical work

- [ ] **P0.11 — Save Bob evidence continuously.** Add clearly named PNG screenshots for every material Bob task under `bob_sessions/`.
- [ ] **P0.12 — Record the live demo path.** Confirm the complete story fits inside 180 seconds, with a precomputed run available if a live Bob task is slow.
- [ ] **P0.13 — Publish a public repository.** Verify README, license, setup instructions, synthetic data statement, source list, and reproducibility commands.
- [ ] **P0.14 — Prepare submission assets.** Cover image, slide deck, public demo URL if available, and MP4 between 90 seconds and 3 minutes.
- [ ] **P0.15 — Fill required statements.** Problem & Solution Statement and Bob Usage Statement, each no more than 500 words.
- [ ] **P0.16 — Submit before 27 September 2026, 22:00 Vietnam time / 23:00 Singapore time.** Do not use the final minutes for screenshots or upload.

## P1 — Stronger evidence

- [ ] Add a held-out fourth scenario selected only after both candidates and the original three results are frozen.
- [ ] Repeat at least one scenario three times to expose agent variance.
- [ ] Add a deliberately neutral scenario where both designs should perform similarly; use it to check whether the comparison exaggerates differences.
- [ ] Add a provenance panel showing Bob task ID, model/account, source commit, scenario hash, test hash, and run command.
- [ ] Add scenario authoring from a roadmap document, but require human selection before execution.
- [ ] Export a self-contained HTML evidence report.
- [ ] Add cancellation, stale-process cleanup, disk quotas, and run-retention policy.

## P2 — Only if the core demo is excellent

- [ ] Parallel Bob tasks for independent scenarios.
- [ ] Automatic candidate-refactor generation and rerun queue, still requiring approval before applying to a real branch.
- [ ] Historical calibration: replay known past features against earlier versions to test whether FutureFork's signals align with observed changes.
- [ ] CI integration that comments with artifact links but never blocks a merge without an explicit policy.
- [ ] Scenario library for API evolution, policy changes, internationalization, storage replacement, and asynchronous workflows.

## Definition of done for every engineering task

- Behavior is exercised, not merely mocked in the UI.
- Tests cover the success case and at least one failure or tampering case.
- The output can be traced to immutable artifacts.
- Documentation is updated when schemas or commands change.
- If Bob performed material work, its task-session screenshot is saved.
- Claims are limited to what was actually run.

