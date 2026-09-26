# FutureFork

**Let your code live through tomorrow before you merge it today.**

FutureFork is an IBM Bob-powered architecture rehearsal tool. Given two code candidates that behave correctly today and a small set of plausible future requirements, it asks Bob to implement the same futures in isolated Git worktrees. It then runs protected acceptance tests and presents inspectable evidence about what each design made easier or harder.

The product does not claim to predict the future or calculate a universal maintainability score. It answers a narrower, useful question:

> Under these stated future-change scenarios, with the same agent, tests, and limits, what actually happened when we tried to evolve each design?

## Why it is different

Most code review tools inspect today's patch. FutureFork performs tomorrow's maintenance work as an experiment. Its primary output is not an opinion: it is a set of disposable implementations, diffs, test results, retries, boundary violations, and a reproducible comparison.

## Canonical demo

Two implementations of the same discount feature pass all current tests:

- `coupled`: discount rules are embedded across checkout, refund, and persistence code.
- `modular`: discount policy is behind a stable interface.

FutureFork sends both designs into three identical futures: partial refunds, organization-specific pricing, and ordered discount composition. Bob implements each future in a separate worktree. The dashboard shows which futures passed, what changed, and where the architecture created friction. Bob then proposes one small present-day refactor and FutureFork reruns a scenario to see whether the measured evidence changes.

See [`docs/DEMO_STORY.md`](docs/DEMO_STORY.md) for the exact script.

## Repository map

| Path | Purpose |
|---|---|
| `CLAUDE.md` | Primary operating instructions for Claude and other coding agents |
| `BACKLOG.md` | Ordered implementation plan and immediate tasks |
| `docs/HACKATHON_SETUP_VI.md` | Vietnamese preflight checklist for registration, IBMid, Bob IDE, Bobcoins, Discord, and submission |
| `docs/PRODUCT_SPEC.md` | Users, jobs, requirements, scope, and claims |
| `docs/ARCHITECTURE.md` | System design, schemas, isolation, and failure handling |
| `docs/DEMO_STORY.md` | Seed application and three-minute demonstration |
| `docs/EVALUATION.md` | Fair-comparison protocol and metrics |
| `docs/BOB_WORKFLOW.md` | Bob IDE, Skill/MCP workflow, Bobcoin plan, and evidence |
| `docs/POSITIONING.md` | Prior art and defensible differentiation |
| `docs/PITCH_AND_SUBMISSION.md` | Submission copy, video outline, and final checklist |
| `docs/DECISIONS.md` | Architectural decision log |
| `scenarios/demo/` | Frozen future-scenario contracts (YAML), `FROZEN.sha256`, and evaluator-owned `protected-tests/` packs with `PACKS.json` hashes ([docs](docs/PROTECTED_TESTS.md)) |
| `futurefork/scenario.py`, `futurefork/testpack.py` | Scenario validator; protected-pack hashing, verification, and mounting |
| `examples/pocketcart/` | Seed app: `coupled` and `modular` candidates, equivalence harness, [README](examples/pocketcart/README.md) |
| `scripts/` | `freeze_scenarios.py`, `freeze_protected_packs.py`, `create_candidate_refs.sh` |
| `tests/` | Root tests: scenario contracts and candidate equivalence |
| `.bob/skills/future-fork/SKILL.md` | Initial Bob skill contract to implement and refine in Bob IDE |
| `bob_sessions/` | Required Bob task-session summary screenshots |
| `artifacts/` | Reproducible run outputs; do not hand-edit results |

## Verify what exists today

```bash
python3 -m venv .venv && .venv/bin/pip install pytest pyyaml pydantic
.venv/bin/python -m pytest -q          # scenario contracts + candidate equivalence
```

## First milestone

Do not start with the dashboard. Build a CLI that can run a single candidate × scenario experiment and write a valid immutable artifact bundle. The dashboard should consume that same bundle later.

The ordered tasks are in [`BACKLOG.md`](BACKLOG.md).

## Honest claim

If completed, the demo supports this statement:

> FutureFork executed the same bounded future-change experiments against two code candidates and produced inspectable evidence about the work required and the resulting behavior.

It does not support “FutureFork proves this architecture is maintainable” or “FutureFork predicts your roadmap.”
