# FutureFork — project instructions

This repository is the IBM Bob 2.0 Hackathon project **FutureFork**.

## Mission

FutureFork helps a developer evaluate a design decision by making IBM Bob implement the same plausible future changes on isolated forks of two code candidates. It reports executed evidence about change friction and can propose a small present-day refactor. Future implementations are experiments and must never be merged automatically.

Canonical one-line pitch:

> FutureFork lets your code live through tomorrow before you merge it today.

## Read this first

1. `README.md` — project overview and repository map.
2. `docs/HACKATHON_SETUP_VI.md` — participant-owned account/setup checklist and contest requirements.
3. `docs/PRODUCT_SPEC.md` — product contract and MVP boundaries.
4. `docs/DEMO_STORY.md` — the exact demo we are building.
5. `docs/ARCHITECTURE.md` — components, data model, and execution flow.
6. `BACKLOG.md` — ordered work; take the first unchecked P0 item unless instructed otherwise.
7. `docs/BOB_WORKFLOW.md` — how IBM Bob must be used and evidenced.
8. `docs/EVALUATION.md` — what counts as valid evidence.

## Non-negotiable rules

- IBM Bob IDE is a core part of the workflow, not a logo or a code-generation footnote.
- Never fabricate Bob sessions, metrics, timings, screenshots, benchmark results, user research, or product claims.
- Label generated future scenarios as hypotheses, not predictions.
- A failed future implementation is not proof that an architecture is bad; it is evidence from one bounded experiment.
- Compare candidates using identical scenarios, acceptance tests, limits, starting environment, and Bob instructions.
- Keep evaluator-owned acceptance tests outside Bob's editable area during each run.
- Never allow an experimental future branch/worktree to modify the source candidates.
- Never merge a future implementation automatically. Only an explicitly approved present-day refactor may be proposed.
- Prefer deterministic observations over LLM judgments. Do not collapse evidence into a mysterious “AI score.”
- All demo data must be synthetic. No client, confidential, personal, or social-media data.
- Every material Bob task needs a task-session summary screenshot in `bob_sessions/` before submission.
- Preserve logs and artifacts needed to reproduce every result shown in the demo.

## MVP definition

The MVP is successful only if it performs one honest end-to-end comparison:

1. Import two Git refs that provide the same current checkout behavior: `coupled` and `modular`.
2. Load three fixed future scenarios and evaluator-owned acceptance tests.
3. Create isolated worktrees for every candidate × scenario pair.
4. Use Bob to implement each scenario under the same limits.
5. Execute protected tests and collect structured evidence.
6. Render a side-by-side evidence matrix with links to diffs and logs.
7. Use Bob to propose one small refactor for the weaker candidate, then rerun one scenario to show whether the evidence improves.

The MVP does not predict real future requirements, prove maintainability, or autonomously merge code.

## Working conventions

- Product/UI language: English for the hackathon submission. Internal planning may be Vietnamese.
- Working title: `FutureFork`; do not spend time renaming until the end-to-end demo works.
- Preferred implementation: Python 3.12 backend/runner, FastAPI, SQLite or filesystem run manifests, React + TypeScript + Vite dashboard, Git worktrees, and a local MCP adapter for Bob.
- Keep the runner usable from a CLI before building the dashboard.
- Store immutable run artifacts under `artifacts/runs/<run-id>/`.
- Store scenario definitions under `scenarios/` as YAML plus protected acceptance tests.
- Any generated claim in the UI must link to a raw artifact: diff, test result, log, or manifest field.

## Current state

Planning and research are documented. P0.1 (scenario contracts) is complete. P0.2 (PocketCart candidates) is complete: baseline commit `0d8b6c2` exists on `main` and the local parentless refs `coupled` and `modular` are created and verified (see `BACKLOG.md`). Nothing is pushed. Claude Code wrote both; no Bob task is associated with them (D012). The protected test packs for all three scenarios are authored and hash-frozen (`docs/PROTECTED_TESTS.md`); they fail on the unchanged candidates as intended, but no implementation has yet been shown to satisfy them.

Verified on 26 September 2026:

- IBM Bob IDE v2.2.0 is installed, logged into the hackathon Enterprise account in `us-east`, and opened on this repository.
- The account began with 40 Bobcoins. A read-only onboarding task used `0.384`; the working remainder is `39.616`.
- The onboarding task is indexed in `bob_sessions/INDEX.md`; its real summary PNG is already in `bob_sessions/`.
- Official Discord channels were identified and are recorded in `docs/HACKATHON_SETUP_VI.md`. Do not post, react, or change Discord state on the user's behalf.
- The participant is solo. Creating a one-person team on lablab.ai is still a user-owned pending action required for submission.
- All current repository content is planning/evidence and is still uncommitted. Preserve it and inspect `git status` before changing files.

## Claude Code handoff

Phase A is complete. The next step is **P0.3**, which is a Bob IDE task run by the user: open Bob IDE on an isolated worktree of one candidate (never the repository root, which contains the protected packs), have Bob implement `partial-refund`, then mount the verified pack and run it.

Before implementation, briefly state the files you plan to create and any schema decision that is not already settled. Do not redesign the product, rename FutureFork, start the dashboard, or skip ahead to P0.2 unless the user explicitly asks.

Claude Code may build the deterministic harness, evaluator, tests, documentation, and UI. It must not fabricate Bob output or silently perform the six candidate future implementations that the evidence matrix attributes to IBM Bob. Those material experiment implementations must be run through Bob IDE and evidenced with real task-session summaries. If Claude Code materially implements another component later, record that role honestly in the final Bob Usage Statement.
