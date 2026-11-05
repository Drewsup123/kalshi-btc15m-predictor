"""Optional live read-only smoke. Disposable state never uses the intended ledger."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from kxbtc15m.client import FeedError, PublicClient
from kxbtc15m.config import DEFAULT_API_BASE, AppConfig
from kxbtc15m.cycle import run_cycle
from kxbtc15m.ledger import Ledger

INTENDED_LEDGER = Path.home() / ".local" / "share" / "kxbtc15m-paper" / "ledger.sqlite"


@unittest.skipIf(os.environ.get("KXBTC15M_SKIP_LIVE") == "1", "live smoke disabled")
class LiveSmokeTests(unittest.TestCase):
    def test_public_gets_only_and_disposable_cycle_isolated(self):
        client = PublicClient(DEFAULT_API_BASE, timeout=20, retries=1)
        try:
            series = client.get_json("/series/KXBTC15M")
        except FeedError as exc:
            self.skipTest(f"live public GET unavailable: {exc}")
        self.assertEqual(series["series"]["ticker"], "KXBTC15M")
        self.assertEqual(series["series"]["fee_type"], "quadratic")
        markets = client.get_json("/markets", {"series_ticker": "KXBTC15M", "status": "open", "limit": "3"})
        self.assertIn("markets", markets)
        if markets["markets"]:
            ticker = markets["markets"][0]["ticker"]
            book = client.get_json(f"/markets/{ticker}/orderbook")
            self.assertIn("orderbook_fp", book)

        with tempfile.TemporaryDirectory() as raw:
            state = Path(raw)
            self.assertNotEqual(state / "ledger.sqlite", INTENDED_LEDGER)
            existed = INTENDED_LEDGER.exists()
            before = INTENDED_LEDGER.stat().st_mtime if existed else None
            ledger = Ledger(state / "ledger.sqlite")
            report = run_cycle(AppConfig(state_dir=state), client, ledger, datetime.now(timezone.utc))
            self.assertIn(report.action, ("entry", "skip", "already_done"))
            self.assertTrue((state / "ledger.sqlite").exists())
            self.assertEqual(INTENDED_LEDGER.exists(), existed)
            if existed:
                self.assertEqual(INTENDED_LEDGER.stat().st_mtime, before)


if __name__ == "__main__":
    unittest.main()
