"""20-second public GET loop. Parent/this-env starts it; not a cloud schedule."""

from __future__ import annotations

import signal
import sys
import time
from pathlib import Path

from kxbtc15m.client import PublicClient
from kxbtc15m.clock import utc_now
from kxbtc15m.config import DEFAULT_API_BASE
from kxbtc15m.openexit.ledger import OpenExitLedger
from kxbtc15m.openexit.lock import WatchLock
from kxbtc15m.openexit.paths import assert_safe_openexit_dir
from kxbtc15m.openexit.tick import run_tick

INTERVAL = 20


def watch_forever(state_dir: Path, api_base: str = DEFAULT_API_BASE, interval: int = INTERVAL) -> int:
    state_dir = assert_safe_openexit_dir(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    log_path = state_dir / "watch.log"
    lock = WatchLock(state_dir)
    lock.acquire()
    stop = {"flag": False}

    def _stop(signum, frame):
        stop["flag"] = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    client = PublicClient(api_base)
    ledger = OpenExitLedger(state_dir / "openexit.sqlite")
    try:
        while not stop["flag"]:
            try:
                result = run_tick(client, ledger, utc_now())
                line = f"{result.get('observed_at')} action={result.get('action')} skip={result.get('skip_reason')} ticker={result.get('market_ticker')}\n"
            except Exception as exc:
                line = f"{utc_now().isoformat()} error={exc}\n"
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(line)
            sys.stdout.write(line)
            sys.stdout.flush()
            for _ in range(interval):
                if stop["flag"]:
                    break
                time.sleep(1)
    finally:
        ledger.close()
        lock.release()
    return 0
