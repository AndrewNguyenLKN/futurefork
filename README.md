# FutureFork

**Let your code live through tomorrow before you merge it today.**

FutureFork is an IBM Bob-powered architecture rehearsal tool. Given two code candidates that
behave correctly today and a frozen, plausible future requirement, it asks Bob to implement that
future in an isolated Git worktree, then runs a hidden, evaluator-owned acceptance test against
the result. It does not claim to predict the future or calculate a universal maintainability
score. It answers a narrower, useful question:

> Under one stated future-change scenario, with the same agent, tests, and limits, what actually
> happened when we tried to evolve each design?

## Current status (read this before anything else)

The pipeline works end to end. **One** of three frozen scenarios (`partial-refund`) has been run
on **both** candidates (`coupled`, `modular`), each through a real IBM Bob task. The other two
frozen scenarios (`organization-pricing`, `ordered-discounts`) are defined and hash-frozen but
have not been run on either candidate — the full 2×3 evidence matrix is not complete. See
[`SUBMISSION_READY.md`](SUBMISSION_READY.md) for the exact asset checklist.

**See the real evidence:** open [`docs/evidence-dashboard.html`](docs/evidence-dashboard.html)
directly in a browser (double-click the file; no server, no network). It reads only real files
under `artifacts/runs/` and `bob_sessions/` — nothing on it is hand-typed. Regenerate it anytime
with `.venv/bin/python scripts/build_dashboard.py` after a new run finalizes.

## Why it is different

Most code review tools inspect today's patch. FutureFork performs tomorrow's maintenance work as
a real, evaluated experiment. Its output is not an opinion: it is a disposable implementation, a
diff, a protected test result, and an immutable, hash-verified artifact bundle.

## Seed application and candidates

PocketCart (`examples/pocketcart/`) is a synthetic checkout service. Two candidates implement the
same current, tested behavior with different designs:

- `coupled`: discount rules are embedded across checkout, refund, and persistence code.
- `modular`: discount policy is behind a stable interface.

The frozen `partial-refund` scenario requires refunded discounts to be allocated deterministically
across items. Bob implemented it independently on both candidates; both pass the same regression
suite and the same 34 hidden acceptance tests for that scenario. See the dashboard for the real
numbers, task IDs, and links to every underlying artifact.

## Try it yourself

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q                 # full test suite (unit + integration, temp repos only)

# the operator-driven CLI (there is no Bob API, so this is two stages, not one atomic command):
export PATH="$(pwd)/.venv/bin:$PATH"
futurefork prepare  --candidate coupled --scenario partial-refund   # stages a worktree, prints its path
#   -> open that worktree in Bob IDE, run the printed task packet, wait for Bob to finish
futurefork finalize --run-id <run-id> --task-id <real-bob-task-id>  # evaluates the result, writes manifest.json
futurefork inspect  --run-id <run-id>                                # check on a run's status
```

## Repository map

| Path | Purpose |
|---|---|
| `CLAUDE.md` | Primary operating instructions for Claude and other coding agents |
| `BACKLOG.md` | Ordered implementation plan and current progress |
| `SUBMISSION_READY.md` | Exact present/missing status of every hackathon submission asset |
| `LICENSE` | MIT |
| `docs/HACKATHON_SETUP_VI.md` | Vietnamese preflight checklist for registration, IBMid, Bob IDE, Bobcoins, Discord, and submission |
| `docs/PRODUCT_SPEC.md` | Users, jobs, requirements, scope, and claims |
| `docs/ARCHITECTURE.md` | System design, schemas, isolation, and failure handling |
| `docs/EVALUATION.md` | Fair-comparison protocol and metrics |
| `docs/PROTECTED_TESTS.md` | How the hidden acceptance packs stay fail-closed and away from Bob |
| `docs/PITCH_AND_SUBMISSION.md` | Problem/Solution and Bob Usage statements, demo script, submission checklist |
| `docs/DECISIONS.md` | Architectural decision log (D001–D020) |
| `docs/evidence-dashboard.html` | **The real, static evidence report** — open directly in a browser |
| `scenarios/demo/` | Frozen scenario contracts (YAML), `FROZEN.sha256`, and evaluator-owned `protected-tests/` packs with `PACKS.json` hashes |
| `futurefork/scenario.py`, `testpack.py`, `manifest.py`, `worktrees.py`, `runner.py`, `cli.py` | Scenario validator; pack hashing/mounting; run-manifest models; isolated Git worktrees; the `prepare`/`finalize` runner; the `futurefork` CLI entry point |
| `schemas/run-manifest.schema.json` | JSON Schema generated from the manifest models (do not hand-edit) |
| `examples/pocketcart/` | Seed app: `coupled` and `modular` candidates, equivalence harness, [README](examples/pocketcart/README.md) |
| `scripts/` | `freeze_scenarios.py`, `freeze_protected_packs.py`, `create_candidate_refs.sh`, `build_dashboard.py` |
| `tests/` | `test_scenarios.py`, `test_pocketcart_equivalence.py`, `test_protected_packs.py`, `test_manifest.py`, `test_worktrees.py`, `test_runner.py` — 553+ tests, temp repos/roots only |
| `.bob/skills/future-fork/SKILL.md` | Planning-stage Bob skill contract; not confirmed as exercised by Bob in any real session — do not claim it was used |
| `bob_sessions/` | Real Bob task-session summary screenshots, indexed in `INDEX.md` |
| `artifacts/runs/` | Immutable, hash-verified run bundles; never hand-edited |

## Honest claim

The demo supports this statement:

> For the frozen `partial-refund` scenario, FutureFork ran the same future-change experiment
> against both `coupled` and `modular` through real IBM Bob tasks, and produced inspectable,
> hash-verified evidence — a patch, a protected test result, and a manifest — for each.

It does not support "FutureFork proves this architecture is maintainable," "FutureFork predicts
your roadmap," or any claim about the other two frozen scenarios, which have not been run.
