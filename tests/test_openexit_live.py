"""Live public-read smoke for the isolated open-exit engine. Disposable temp state."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from kxbtc15m.client import FeedError, PublicClient
from kxbtc15m.config import DEFAULT_API_BASE
from kxbtc15m.openexit.ledger import OpenExitLedger
from kxbtc15m.openexit.tick import run_tick
from kxbtc15m.schema import unwrap_market

PARENT = Path("/workspace/personal-finance/kalshi-paper/state/ledger.sqlite")
INTENDED = Path.home() / ".local" / "share" / "kxbtc15m-paper-openexit" / "openexit.sqlite"


@unittest.skipIf(os.environ.get("KXBTC15M_SKIP_LIVE") == "1", "live smoke disabled")
class OpenExitLiveSmokeTests(unittest.TestCase):
    def test_public_read_tick_on_temp_state(self):
        client = PublicClient(DEFAULT_API_BASE, timeout=20, retries=1)
        try:
            raw = client.get_json("/markets/KXBTC15M-26NOV051445-45")
        except FeedError as exc:
            self.skipTest(f"live public GET unavailable: {exc}")
        market = unwrap_market(raw)
        self.assertIsNotNone(market)
        self.assertEqual(market["ticker"], "KXBTC15M-26NOV051445-45")
        self.assertIn(str(market.get("result") or "").lower(), {"yes", "no", ""})

        with tempfile.TemporaryDirectory() as raw_dir:
            state = Path(raw_dir)
            existed_parent = PARENT.exists()
            existed_intended = INTENDED.exists()
            parent_mtime = PARENT.stat().st_mtime if existed_parent else None
            ledger = OpenExitLedger(state / "openexit.sqlite")
            try:
                out = run_tick(client, ledger, datetime.now(timezone.utc))
            finally:
                ledger.close()
            self.assertIn(out["action"], ("entry", "skip", "idle", "hold", "already_done", "official_settlement"))
            self.assertTrue((state / "openexit.sqlite").exists())
            self.assertFalse((state / "ledger.sqlite").exists())
            self.assertEqual(PARENT.exists(), existed_parent)
            self.assertEqual(INTENDED.exists(), existed_intended)
            if existed_parent:
                self.assertEqual(PARENT.stat().st_mtime, parent_mtime)
            self.assertNotEqual(out["observed_at"], market.get("close_time"))


if __name__ == "__main__":
    unittest.main()
