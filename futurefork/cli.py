"""`futurefork` command-line entry point.

Two-stage, operator-driven workflow (there is no Bob API):

    futurefork prepare  --candidate <ref> --scenario <id-or-path> [--run-id ...]
    # -> open the printed worktree path in Bob IDE, run the task packet, wait for Bob to finish
    futurefork finalize --run-id <id> --task-id <bob-task-id> [--attempts N]
    futurefork inspect  --run-id <id>
    futurefork cleanup  --run-id <id>

`futurefork run` (single-shot) is deliberately not offered: it would imply Bob ran automatically,
which is not true for this MVP.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import manifest as mf
from . import runner


def _resolve_scenario(config: runner.RunnerConfig, value: str) -> Path:
    path = Path(value)
    if path.is_file():
        return path
    candidate = config.repo / "scenarios" / "demo" / f"{value}.yaml"
    if candidate.is_file():
        return candidate
    raise runner.RunnerError(f"scenario not found: {value!r} (tried {path} and {candidate})")


def _config_from_args(args: argparse.Namespace) -> runner.RunnerConfig:
    repo = Path(args.repo).resolve() if args.repo else runner.default_config().repo
    base = runner.default_config(repo)
    runs_root = Path(args.runs_root).resolve() if args.runs_root else base.runs_root
    worktree_root = Path(args.worktree_root).resolve() if args.worktree_root else base.worktree_root
    return runner.RunnerConfig(repo=repo, runs_root=runs_root, worktree_root=worktree_root)


def _add_common(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--repo", help="FutureFork project root (default: this package's own repository)")
    ap.add_argument("--runs-root", help="override the run-directory root (default: <repo>/artifacts/runs)")
    ap.add_argument("--worktree-root", help="override the WorktreeManager root (default: OS temp dir)")


def _cmd_prepare(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    scenario_path = _resolve_scenario(config, args.scenario)
    result = runner.prepare(config, args.candidate, scenario_path, run_id=args.run_id)
    print(f"run_id: {result.run_id}")
    print(f"run directory: {result.run_dir}")
    if result.outcome is not None:
        print(f"outcome: {result.outcome.value} (no agent work was needed; see {result.run_dir / runner.MANIFEST_FILE})")
        if result.worktree_path is not None:
            print(f"worktree preserved for inspection: {result.worktree_path}")
            print(f"  remove it with: futurefork cleanup --run-id {result.run_id}")
        return 0
    print(f"worktree: {result.worktree_path}")
    print(f"task packet: {result.task_packet_path}")
    print()
    print(f"Next: open {result.worktree_path} in Bob IDE and run the task packet above.")
    print(f"When Bob's task ends, run:")
    print(f"  futurefork finalize --run-id {result.run_id} --task-id <bob-task-id>")
    return 0


def _cmd_finalize(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    try:
        result = runner.finalize(config, args.run_id, task_id=args.task_id,
                                 human_triggered=not args.not_human_triggered, attempts=args.attempts)
    except runner.RunAlreadyFinalizedError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    print(f"run_id: {result.run_id}")
    print(f"outcome: {result.outcome.value}")
    print(f"manifest: {result.manifest_path}")
    if result.cleanup_error:
        print(f"WARNING: worktree cleanup failed and was preserved: {result.cleanup_error}", file=sys.stderr)
        print(f"  retry with: futurefork cleanup --run-id {result.run_id}", file=sys.stderr)
        return 2
    return 0 if result.outcome is mf.Outcome.COMPLETED else 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    status = runner.inspect(config, args.run_id)
    print(f"run_id: {status.run_id}")
    print(f"prepared: {status.prepared}")
    print(f"finalized: {status.finalized}")
    if status.outcome is not None:
        print(f"outcome: {status.outcome.value}")
    if status.worktree_path is not None:
        print(f"worktree (awaiting finalize): {status.worktree_path}")
    return 0


def _cmd_cleanup(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    runner.cleanup(config, args.run_id)
    print(f"removed the worktree for run {args.run_id}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="futurefork", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("prepare", help="validate candidate+scenario and stage a worktree for Bob")
    _add_common(p)
    p.add_argument("--candidate", required=True, help="candidate ref, e.g. 'modular' or 'coupled'")
    p.add_argument("--scenario", required=True, help="scenario id (e.g. 'partial-refund') or a YAML path")
    p.add_argument("--run-id", help="explicit run id (mainly for scripting/tests); default: generated from now()")
    p.set_defaults(func=_cmd_prepare)

    f = sub.add_parser("finalize", help="evaluate a completed Bob task and write the run manifest")
    _add_common(f)
    f.add_argument("--run-id", required=True)
    f.add_argument("--task-id", required=True, help="the real Bob task id; never fabricate this")
    f.add_argument("--not-human-triggered", action="store_true",
                   help="record agent.human_triggered=false (default: true, since Bob is operator-driven here)")
    f.add_argument("--attempts", type=int, default=1,
                   help="operator-reported count of Bob implementation attempts inside the IDE (default: 1)")
    f.set_defaults(func=_cmd_finalize)

    i = sub.add_parser("inspect", help="show the status of a prepared or finalized run")
    _add_common(i)
    i.add_argument("--run-id", required=True)
    i.set_defaults(func=_cmd_inspect)

    c = sub.add_parser("cleanup", help="remove a retained worktree (e.g. after setup_failed)")
    _add_common(c)
    c.add_argument("--run-id", required=True)
    c.set_defaults(func=_cmd_cleanup)

    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except runner.RunnerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
