"""Paper-only CLI: cycle (mutate) and status (read-only)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from kxbtc15m.client import PublicClient
from kxbtc15m.clock import utc_now
from kxbtc15m.config import load_config
from kxbtc15m.cycle import run_cycle
from kxbtc15m.ledger import Ledger
from kxbtc15m.report import Report, build_report, format_json, format_text


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
    sub.add_parser("cycle", help="Settle, discover, snapshot, signal, risk, simulate.", parents=[common])
    sub.add_parser("status", help="Read-only ledger scorecard.", parents=[common])
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


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
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
