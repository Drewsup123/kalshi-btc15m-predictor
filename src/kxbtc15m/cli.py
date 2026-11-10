"""Paper-only CLI: baseline cycle/status plus isolated open-exit run/watch/report."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from kxbtc15m.client import PublicClient
from kxbtc15m.clock import utc_now
from kxbtc15m.config import DEFAULT_API_BASE, load_config
from kxbtc15m.cycle import run_cycle
from kxbtc15m.ledger import Ledger
from kxbtc15m.openexit.compare import build_compare, format_compare_text
from kxbtc15m.openexit.ledger import OpenExitLedger
from kxbtc15m.openexit.paths import assert_safe_openexit_dir
from kxbtc15m.openexit.tick import run_tick
from kxbtc15m.openexit.watch import watch_forever
from kxbtc15m.report import Report, build_report, format_json, format_text

DEFAULT_OPENEXIT_DIR = Path.home() / ".local" / "share" / "kxbtc15m-paper-openexit"
PARENT_BASELINE_LEDGER = Path("/workspace/personal-finance/kalshi-paper/state/ledger.sqlite")


def _common() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--state-dir", help="Persistent state directory (ledger + snapshots).")
    common.add_argument("--api-base", help="Official public Trade API base URL.")
    common.add_argument("--model-version", help="Override experimental model_version string.")
    return common


def _parser() -> argparse.ArgumentParser:
    common = _common()
    parser = argparse.ArgumentParser(
        prog="kxbtc15m",
        description="Personal paper-only Kalshi KXBTC15M simulator (no live orders).",
        parents=[common],
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("cycle", help="Baseline only: settle/discover/snapshot/signal/risk/simulate.", parents=[common])
    sub.add_parser("status", help="Baseline only: read-only scorecard.", parents=[common])
    sub.add_parser("run", help="Open-exit: one 20s-style tick on the isolated ledger.", parents=[common])
    watch = sub.add_parser("watch", help="Open-exit: 20s public GET loop (singleton lock).", parents=[common])
    watch.add_argument("--interval", type=int, default=20)
    report = sub.add_parser("report", help="15-minute compare (read-only). Does not create the baseline ledger.", parents=[common])
    report.add_argument("--baseline-state-dir", help="Directory that already holds the original ledger.sqlite")
    sub.add_parser("v3-inventory", help="V3: page public settled KXBTC15M (GET only) into an isolated dir.", parents=[common])
    sub.add_parser("v3-evaluate", help="V3: replay fit on train/val, lock, one holdout pass.", parents=[common])
    sub.add_parser("v3-screen", help="V3: write local read-only results.html.", parents=[common])
    return parser


def _print_report(report: Report) -> None:
    sys.stdout.write(format_json(report))
    sys.stdout.write("\n\n")
    sys.stdout.write(format_text(report))
    sys.stdout.write("\n")


def _status(cfg) -> int:
    if not cfg.ledger_path.is_file():
        sys.stdout.write(
            json_no_ledger()
            + "\n\nKXBTC15M personal paper status\nNo ledger at "
            + str(cfg.ledger_path)
            + "\nRun `cycle` first. Status is read-only and did not create one.\n"
        )
        return 0
    ledger = Ledger(cfg.ledger_path, readonly=True)
    try:
        report = build_report(ledger, utc_now(), cfg.model_version, action="status", data_health="read_only")
        _print_report(report)
    finally:
        ledger.close()
    return 0


def json_no_ledger() -> str:
    return '{\n  "action": "status",\n  "skip_reason": "no_ledger"\n}'


def _openexit_dir(args) -> Path:
    chosen = args.state_dir or os.environ.get("KXBTC15M_OPENEXIT_STATE_DIR") or DEFAULT_OPENEXIT_DIR
    return assert_safe_openexit_dir(chosen)


def _run_openexit(args) -> int:
    state = _openexit_dir(args)
    state.mkdir(parents=True, exist_ok=True)
    ledger = OpenExitLedger(state / "openexit.sqlite")
    client = PublicClient(args.api_base or os.environ.get("KXBTC15M_API_BASE") or DEFAULT_API_BASE)
    try:
        result = run_tick(client, ledger, utc_now())
        sys.stdout.write(json.dumps(result, indent=2, sort_keys=True))
        sys.stdout.write("\n")
        return 0
    finally:
        ledger.close()


def _report(args) -> int:
    baseline_dir = Path(
        args.baseline_state_dir
        or os.environ.get("KXBTC15M_STATE_DIR")
        or PARENT_BASELINE_LEDGER.parent
    ).expanduser()
    baseline_ledger = baseline_dir / "ledger.sqlite"
    openexit_dir = _openexit_dir(args)
    payload = build_compare(baseline_ledger, openexit_dir)
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
    sys.stdout.write("\n\n")
    sys.stdout.write(format_compare_text(payload))
    sys.stdout.write("\n")
    return 0


def _v3_dir(args) -> Path:
    from kxbtc15m.v3.paths import assert_safe_v3_dir

    chosen = args.state_dir or os.environ.get("KXBTC15M_V3_STATE_DIR") or str(Path("var/v3"))
    return assert_safe_v3_dir(chosen)


def _v3(args) -> int:
    from kxbtc15m.v3.pipeline import run_evaluate_cached, run_inventory, run_screen

    state = _v3_dir(args)
    api_base = args.api_base or os.environ.get("KXBTC15M_API_BASE") or DEFAULT_API_BASE
    if args.command == "v3-inventory":
        report = run_inventory(state, api_base)
        sys.stdout.write(json.dumps(report, indent=2, default=str) + "\n")
        return 0
    if args.command == "v3-evaluate":
        metrics = run_evaluate_cached(state)
        sys.stdout.write(json.dumps({
            "run_generated_at": metrics.get("run_generated_at"),
            "n_holdout": metrics.get("n_holdout"),
            "holdout_A_accuracy": (metrics.get("holdout") or {}).get("A_logistic", {}).get("accuracy"),
            "availability": metrics.get("availability"),
        }, indent=2) + "\n")
        return 0
    if args.command == "v3-screen":
        path = run_screen(state)
        sys.stdout.write(str(path) + "\n")
        return 0
    raise RuntimeError(args.command)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if str(args.command).startswith("v3-"):
        return _v3(args)
    if args.command == "run":
        return _run_openexit(args)
    if args.command == "watch":
        return watch_forever(
            _openexit_dir(args),
            api_base=args.api_base or os.environ.get("KXBTC15M_API_BASE") or DEFAULT_API_BASE,
            interval=getattr(args, "interval", 20),
        )
    if args.command == "report":
        return _report(args)
    cfg = load_config(
        state_dir=args.state_dir,
        api_base=args.api_base,
        model_version=args.model_version,
    )
    if args.command == "status":
        return _status(cfg)
    Path(cfg.state_dir).mkdir(parents=True, exist_ok=True)
    ledger = Ledger(cfg.ledger_path, starting_cash_cents=cfg.starting_cash_cents)
    client = PublicClient(cfg.api_base)
    try:
        report = run_cycle(cfg, client, ledger, utc_now())
        _print_report(report)
        return 0
    finally:
        ledger.close()


if __name__ == "__main__":
    raise SystemExit(main())
