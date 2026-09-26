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
