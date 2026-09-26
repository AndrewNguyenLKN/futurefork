# Protected acceptance test packs

Evaluator-owned, black-box acceptance tests for the three frozen scenarios. They are the oracle: Bob may not see, edit, or run them while implementing a future.

| Scenario | Pack | Tests |
|---|---|---|
| `partial-refund` | `scenarios/demo/protected-tests/partial-refund/` | 34 (1 guard) |
| `organization-pricing` | `scenarios/demo/protected-tests/organization-pricing/` | 28 (3 guards) |
| `ordered-discounts` | `scenarios/demo/protected-tests/ordered-discounts/` | 115 (1 guard) |

Each pack holds `test_*.py`, `conftest.py`, `support.py` (a WSGI client that uses only `pocketcart.create_app()`), and `oracle_model.py` (an executable statement of the scenario's frozen `rules`, itself unit-tested in `tests/test_protected_packs.py` against hand-derived numbers). Counts come from the last verified run and are enforced only by the pack hashes.

## What the tests are based on

Only the scenario's frozen `public_interface` (endpoints, error codes, rules) plus the current PocketCart contract. Two tolerances follow from the interface being silent:

- The order of `items` in a refund response and whether a 0-cent discount component is listed are not specified, so tests do not depend on either.
- `refund_id` sequencing across failed requests, order `status` after a partial refund, and atomicity of a multi-item request are not specified and are not tested.

**One test seam that is not in the interface.** The rule "refund amounts must not depend on coupon definitions as they are at refund time" can only be observed by changing a coupon after checkout. The partial-refund pack does that through the existing `pocketcart.catalog.COUPONS` mapping (`test_refund_uses_pricing_recorded_at_checkout_not_todays_coupon`). If Bob moves or renames that mapping, this one test fails with `AttributeError`/`KeyError` for a reason unrelated to the requirement. Treat that outcome as `runner_error`-adjacent and review it by hand; do not count it silently against a candidate.

## Guards and future-behavior tests

Tests marked `@pytest.mark.guard` describe behavior that must already hold (for example, the existing full refund, or the consumer JSON being unchanged) and must keep passing. Every other test requires the future behavior. `tests/test_protected_packs.py` proves, for both unchanged candidates:

- every pack collects cleanly (no import errors);
- all guards pass;
- every future-behavior test fails, none pass by accident, none error or skip, and each failure is a failed assertion (not a `KeyError`/`TypeError` inside the test code);
- both candidates produce the same pass/fail set (the oracle does not favor either design).

**What this does not prove.** No working implementation of any future exists, so it is not yet demonstrated that each pack is *satisfiable*. The oracle arithmetic was derived by hand and by the executable models, which agree; the first real check is P0.3. If Bob's result fails a protected test in a way that looks like an oracle error, record it as evaluator error and fix the pack before rerunning both candidates.

## Hashes

`scenarios/demo/protected-tests/PACKS.json` records, per scenario, the SHA-256 of every file and one pack hash. The pack hash is SHA-256 over the sorted lines `"<file sha256>  <relative path>\n"`, so an edit, addition, deletion, or rename changes it. `__pycache__`, `.pytest_cache`, and `*.pyc` are ignored (running tests creates them); symlinks are rejected.

```bash
.venv/bin/python scripts/freeze_protected_packs.py show    # print pack hashes
.venv/bin/python scripts/freeze_protected_packs.py check   # verify against PACKS.json
.venv/bin/python scripts/freeze_protected_packs.py write   # deliberate re-freeze after an intentional edit
```

Re-freezing is a deliberate act: it changes the `evaluator.test_pack_sha256` recorded in future manifests, so results from before and after are not comparable. Do not re-freeze between the two candidates' runs of one scenario.

## How the packs stay away from Bob

Layers, from strongest to weakest:

1. **Placement.** Packs live under `scenarios/demo/protected-tests/`, outside `examples/pocketcart/candidates/`. `scripts/create_candidate_refs.sh` snapshots only the candidate directory, so no candidate ref can contain a pack, and a worktree created from a candidate ref cannot either. `tests/test_protected_packs.py` asserts that candidate files never name a pack, the mount path, or `oracle_model`.
2. **Bob's workspace is the worktree only.** For each run, open Bob IDE on the isolated worktree folder, never on the FutureFork repository root. The repository root contains the packs, `PACKS.json`, and the scenario YAMLs; a Bob task opened there can read them. This is procedure, not technical enforcement.
3. **Mounted after editing stops.** The runner mounts the pack into the finished worktree at the scenario's `protected_tests.mount` (`.futurefork-evaluator/<id>`) only after Bob's edits are frozen. `futurefork.testpack.mount_pack` verifies the source against `PACKS.json`, refuses an existing destination, copies, makes the files read-only, and re-verifies the copy. The scenario's `editable_paths` (`src/**`, `tests/**`) and `protected_paths` (`.futurefork-evaluator/**`) are disjoint, which the scenario validator enforces.
4. **Detection.** Any pack that differs from `PACKS.json` (modified, added, removed, renamed) fails verification before tests run, and the run must be classed `oracle_tampered`. This is tamper *detection*, not prevention: a read-only mount can be `chmod`ed by the same user.
5. **Public packet excludes the oracle.** The scenario YAML that Bob sees never names the pack, and `tests/test_scenarios.py` checks the public interface contains neither "protected" nor the mount path.

**Residual risks, stated plainly.** Nothing here is an operating-system sandbox. A Bob task with access to the FutureFork repository root could read a pack; the defense is opening it on the worktree only, plus the honesty of the run record (log the workspace path in the manifest). Hidden-test contents are also indirectly inferable from the public rules, which is by design: the interface must be specified for the comparison to be fair. P0.5 (isolated worktrees) and P0.7 (protect the oracle: hash before and after execution, fail closed) build on the helpers above and remain open.
