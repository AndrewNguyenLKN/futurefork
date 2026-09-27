# Decision log

## D001 — Compare executions, not an opaque quality score

**Status:** accepted

FutureFork presents test outcomes and raw change evidence. It will not create a universal “maintainability score” for the MVP because weights would encode arbitrary preferences and imply unjustified precision.

## D002 — Use two behaviorally equivalent candidates

**Status:** accepted

The canonical evaluation compares code designs, not a broken implementation against a correct one. Both candidates must pass the same current contract before any future experiments.

## D003 — Protect acceptance tests from Bob

**Status:** accepted

Bob may write development tests, but scenario acceptance tests are evaluator-owned, hidden during editing, inserted or mounted after editing, and hash-verified.

## D004 — Future branches are disposable

**Status:** accepted

Scenario implementations are experimental evidence. They are never merged automatically. Only a small present-day refactor may be proposed, and applying it requires explicit human approval.

## D005 — Bob is the implementer; deterministic tools are the evaluator

**Status:** accepted

This creates a meaningful IBM Bob story without asking an LLM to grade its own output.

## D006 — CLI and artifact schema before dashboard

**Status:** accepted

The dashboard consumes real artifacts from the same CLI used in evaluation. No hardcoded demo results are allowed.

## D007 — Python runner, React dashboard

**Status:** proposed; revisit only before code begins

Python provides fast process/Git orchestration, test integration, Pydantic schemas, FastAPI, and MCP options. React/Vite provides a polished evidence UI. If the first Bob implementation strongly favors a single TypeScript stack, record the change here before diverging.

## D008 — PocketCart and discount evolution as the seed domain

**Status:** accepted for MVP

Pricing, refunds, and policy composition create understandable consequences without external data. The seed app must remain realistic enough that neither candidate is an obvious straw man.


## D009 — Scenario commands are argv arrays

**Status:** accepted (2026-09-26, pending user review)

`setup_command`, `dev_test_command`, `protected_test_command`, and `command_allowlist` entries are lists of strings, never shell fragments, following the "argument arrays where possible" guidance in `docs/ARCHITECTURE.md`. `setup_command: []` means no setup step: PocketCart has no runtime dependencies and the demo denies network access, so the evaluator toolchain supplies `pytest`. `docs/ARCHITECTURE.md` originally showed strings and `uv sync --frozen`; `uv` is not installed on the development machine and no lockfile exists.

## D010 — Scenarios carry a frozen public interface and a hypothesis label

**Status:** accepted (2026-09-26, pending user review)

Hidden black-box acceptance tests are only fair if the interface they call is specified. Each scenario therefore has a `public_interface` block (HTTP endpoints, error codes, and exact rules such as the refund-allocation and discount-ordering arithmetic) that is part of the packet Bob sees, and a required `label: hypothesis`. The block is an elaboration, chosen by the evaluator, of the requirement in `docs/DEMO_STORY.md`; requirement text is asserted verbatim by `tests/test_scenarios.py`. Each scenario is applied independently to the same starting checkout, so organization pricing (F2) and ordered discounts (F3) each define their own organization registry. Limits, editable paths, commands, and allowlist are identical across scenarios, and `scenarios/demo/FROZEN.sha256` freezes the YAML bytes (`scripts/freeze_scenarios.py write|check`). The protected test packs themselves are not yet authored.

## D011 — Candidate refs are parentless commits made with Git plumbing

**Status:** accepted (2026-09-26)

`coupled` and `modular` are meant to be Git refs, but the repository has no commits and committing is the user's decision. Candidates live as directories under `examples/pocketcart/candidates/`; `scripts/create_candidate_refs.sh` builds the refs later as parentless commits without touching the working tree, index, or HEAD, and refuses to overwrite. The equivalence checker accepts `--refs` and is tested against refs built in a temporary repository.

## D012 — Disclosure: seed application authorship

**Status:** recorded (2026-09-26)

Claude Code (not IBM Bob) wrote the P0.1 scenario contracts and validators and the P0.2 PocketCart candidates, tests, and equivalence harness. No Bob task exists for them and none is claimed. The final Bob Usage Statement must describe this role split accurately. The six candidate-by-scenario future implementations remain reserved for Bob IDE.

## D013 — Protected packs: black-box, guarded, hash-frozen

**Status:** accepted (2026-09-26)

Each frozen scenario has an evaluator-owned pack under `scenarios/demo/protected-tests/<id>/` that drives only `pocketcart.create_app()` over WSGI and asserts against the scenario's frozen `public_interface`. Tests are either *guards* (already hold; must not regress) or future-behavior tests (must fail on the unchanged candidates). Expected numbers are hand-derived and cross-checked against an executable `oracle_model.py` per pack. Packs are frozen in `PACKS.json` (per-file and pack SHA-256); any modified, added, removed, or renamed file fails verification. Known limitation: no future has been implemented, so pack satisfiability is unproven until P0.3. One test uses the existing `catalog.COUPONS` mapping as a seam (see `docs/PROTECTED_TESTS.md`). Claude Code wrote the packs; no Bob task is involved.

## D014 — Outcome taxonomy: ARCHITECTURE.md is canonical

**Status:** accepted (2026-09-27)

`docs/PRODUCT_SPEC.md` listed five statuses (`completed`, `tests_failed`, `budget_exhausted`, `invalid`, `runner_error`); `docs/ARCHITECTURE.md` lists eight. The manifest uses the eight in ARCHITECTURE: `candidate_invalid`, `setup_failed`, `budget_exhausted`, `regression_failed`, `acceptance_failed`, `oracle_tampered`, `runner_error`, `completed`. The old `tests_failed` splits into `regression_failed` and `acceptance_failed`; `invalid` splits into `candidate_invalid`, `setup_failed`, and `oracle_tampered`. `tests/test_manifest.py` parses the ARCHITECTURE taxonomy and asserts the enum matches it. Outcomes are grouped as experimental, integrity, and infrastructure so infrastructure failures are never scored against a candidate: they cannot carry a `failed` test state.

## D015 — Manifest test results are objects, and the pack hash is observed twice

**Status:** accepted (2026-09-27)

The ARCHITECTURE example showed `"tests": {"regression": "passed", "protected": "passed"}`. That cannot distinguish `error` from `failed` or carry commands and counts, so each is an object (`state`, `command`, `returncode`, counts, optional `results_artifact`). `evaluator` gains `observed_sha256_after_run` next to the frozen hash so `completed` (equal) and `oracle_tampered` (different) can be checked mechanically. Events carry `provenance: observed|reported` so unverified operator statements, like several in the P0.3 run, stay distinguishable from evaluator observations.

## D016 — One definition: the JSON Schema is generated from the models

**Status:** accepted (2026-09-27)

`schemas/run-manifest.schema.json` is written by `python -m futurefork.manifest schema --write` and a test compares it byte-for-byte with the model output. Path and ref safety patterns use lookaheads and therefore `regex_engine="python-re"`; they are defined once and appear identically in the schema. JSON Schema cannot express the outcome and cross-reference invariants, so consumers must use `load_manifest`. Timestamps are UTC whole seconds so `run_id` (which embeds the start time) and serialization are exactly reproducible. `manifest.json` cannot list itself as an artifact. The model checks that listed artifacts exist as entries and have the right kind where a kind is required (see D017); it does **not** read files, so it cannot check that a listed hash matches bytes on disk, only that the record is well-formed. Verifying hashes against files is the runner's job (P0.6/P0.7). No existing P0.3 artifact was modified or given a manifest; retrofitting one is a separate, explicit step.

## D017 — A completed manifest must carry the evidence bundle; the model enforces it

**Status:** accepted (2026-09-27), after independent review of P0.4

`docs/ARCHITECTURE.md` says every run directory should contain the evidence bundle, and a `completed` result is the one claim the whole comparison rests on, so the model enforces it for `completed` rather than leaving it to the P0.6 runner: artifact kinds `scenario`, `task_packet`, `patch`, `changed_paths`, `test_results`, `measurements`, `events`, `stdout_log`, `stderr_log`, `artifact_hashes` must all be listed; each test run must record its command, `returncode` 0, and a `results_artifact` of kind `test_results` or `junit_xml`. Counts alone are self-reported and are not evidence. Failed, tampered, and infrastructure outcomes are not held to the full bundle (a run that died in setup cannot have produced it); they keep the evidence their own invariants require. Review also fixed three defects in the first P0.4 cut: a `failed` or `error` test with `returncode` 0 was accepted, and `results_artifact` was not kind-checked (both now rejected).

## D018 — Worktree isolation: OID once, exact-path cleanup only, reservation for concurrency

**Status:** accepted (2026-09-27)

`WorktreeManager` resolves a candidate ref to a commit OID exactly once (`resolve`), builds the detached worktree from that OID (never the ref name, so a ref that moves mid-call cannot change what is built), and re-verifies the ref/OID/tree and any `watch_refs` on exit. The worktree root is explicit and validated (absolute, private, not overlapping the repository or declared oracle/protected-test paths); the default for production is `tempfile.gettempdir()`, outside any repository. Run ids reuse the manifest's `RUN_ID_PATTERN`. Concurrency safety is one `O_EXCL` reservation file per run id (atomic on POSIX); collisions are typed as path, registered-worktree, or run-id-in-use. Cleanup is exactly `git worktree remove --force <recorded path>`, checked against the path the manager itself computed for that run id; on any failure the worktree is left in place and `CleanupError` is raised, never a fallback deletion. This is a direct, structural response to the P0.3 incident, where `shutil.rmtree(dest.parent.parent)` deleted an entire worktree; `tests/test_worktrees.py` reproduces that exact shape as a regression test. Errors are typed with a `manifest_outcome` (`candidate_invalid` for problems with the candidate itself; `runner_error` for everything else), so a P0.6 runner can record outcomes consistently with the P0.4 taxonomy without inventing its own mapping.

## D019 — Fixed in passing: a `$`-anchored pattern accepted a trailing newline (P0.4)

**Status:** accepted (2026-09-27)

While starting P0.5, `ref`, `starting_commit`, and other manifest patterns were found to accept a value with a trailing `\n`, because Python's `$` also matches immediately before a final newline. All manifest regex patterns are now built through `_anchored()`, which appends `(?!\n)`. `tests/test_manifest.py` gained a component-level test (`test_no_pattern_accepts_a_trailing_newline_in_isolation`) so a similarly-scoped leak cannot hide behind a cross-field check again. This did not change the checked-in JSON Schema's semantics beyond the pattern strings themselves; `schema --check` was regenerated and passes.

## D020 — The runner CLI is two operator-driven stages, not one `futurefork run`

**Status:** accepted (2026-09-27)

`docs/ARCHITECTURE.md`'s illustrative `futurefork run --candidate <ref> --scenario <yaml>` implies
one atomic command, but there is no Bob API to automate the middle of it. `futurefork prepare`
validates the candidate and scenario, creates a retained detached worktree via `WorktreeManager`,
and writes the public task packet — the protected pack is never exposed at this stage. The operator
opens that worktree in Bob IDE, runs the task packet, and only once Bob's task has ended calls
`futurefork finalize --run-id <id> --task-id <real-bob-task-id>`, which freezes the patch, mounts
and verifies the protected pack (P0.7), runs regression then protected tests under the scenario's
limits, re-verifies the pack afterward, and writes the full evidence bundle and manifest. `inspect`
and `cleanup` round out the lifecycle (checking on, or disposing of, a run that never reached
`finalize`). This keeps the tool honest: nothing claims Bob ran automatically, and every `task_id`
in a manifest is one the operator actually typed in after a real Bob session.

Pre-agent outcomes (`candidate_invalid`, `setup_failed`) are written by `prepare` itself, since they
happen before Bob ever gets a task id, matching the manifest's own `_NO_AGENT_YET` rule (D014).
`finalize` is safely resumable: every artifact it writes before `manifest.json` is a plain
overwrite, and a leftover, byte-verified pack mount from an interrupted attempt is cleared before
remounting — the only `shutil.rmtree` in `futurefork/runner.py`, and only ever on that one exact,
just-verified path (`tests/test_runner.py::test_no_broad_deletion_apis_in_the_runner_source`).
