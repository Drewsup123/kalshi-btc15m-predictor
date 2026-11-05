import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from kxbtc15m.cli import main
from kxbtc15m.client import FeedError, PublicClient


class CliTests(unittest.TestCase):
    def test_status_is_read_only_when_missing_ledger(self):
        with tempfile.TemporaryDirectory() as raw:
            state = Path(raw)
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(["status", "--state-dir", str(state)])
            self.assertEqual(code, 0)
            self.assertFalse((state / "ledger.sqlite").exists())
            self.assertIn("no ledger", buf.getvalue().lower())

    def test_status_does_not_write_after_cycle(self):
        with tempfile.TemporaryDirectory() as raw:
            state = Path(raw)
            from tests.test_cycle import NOW, _cfg, _client
            from kxbtc15m.cycle import run_cycle
            from kxbtc15m.ledger import Ledger

            ledger = Ledger(state / "ledger.sqlite")
            run_cycle(_cfg(state), _client(), ledger, NOW)
            before = (state / "ledger.sqlite").read_bytes()
            events_before = ledger.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(["status", "--state-dir", str(state)])
            self.assertEqual(code, 0)
            ledger2 = Ledger(state / "ledger.sqlite")
            events_after = ledger2.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            self.assertEqual(events_before, events_after)
            self.assertEqual(before, (state / "ledger.sqlite").read_bytes())
            self.assertIn("cash", buf.getvalue().lower())

    def test_cycle_cli_uses_temp_state_not_default_live(self):
        with tempfile.TemporaryDirectory() as raw:
            state = Path(raw)
            intended = Path("/tmp/kxbtc15m-intended-starting-ledger")
            self.assertNotEqual(state, intended)
            from tests.test_cycle import NOW, _client

            buf = io.StringIO()
            with (
                redirect_stdout(buf),
                patch("kxbtc15m.cli.PublicClient", return_value=_client()),
                patch("kxbtc15m.cli.utc_now", return_value=NOW),
            ):
                code = main(["cycle", "--state-dir", str(state)])
            self.assertEqual(code, 0)
            self.assertTrue((state / "ledger.sqlite").exists())
            self.assertFalse(intended.exists())
            payload = json.loads(buf.getvalue().split("\n\n", 1)[0])
            self.assertIn(payload["action"], ("entry", "skip"))

    def test_cycle_cli_settles_nested_official_envelope(self):
        from datetime import datetime, timezone

        from kxbtc15m.ledger import Ledger
        from tests.test_cycle import _client
        from tests.test_settle_unwrap import OFFICIAL_NESTED_YES, TICKER

        later = datetime(2026, 11, 5, 20, 40, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as raw:
            state = Path(raw)
            ledger = Ledger(state / "ledger.sqlite")
            ledger.open_position(
                cycle_id="2026-11-05T19:45:00Z",
                market_ticker=TICKER,
                side="no",
                contracts=15,
                cost_cents=92,
                fee_cents=7,
                debit_cents=99,
                ask_dollars="0.0613",
                model_version="exp-baseline-v1@2026-11-05",
                entry_class="experimental",
                opened_at="2026-11-05T19:39:00Z",
            )
            ledger.close()
            buf = io.StringIO()
            with (
                redirect_stdout(buf),
                patch("kxbtc15m.cli.PublicClient", return_value=_client(**{TICKER: OFFICIAL_NESTED_YES})),
                patch("kxbtc15m.cli.utc_now", return_value=later),
            ):
                code = main(["cycle", "--state-dir", str(state)])
            self.assertEqual(code, 0)
            payload = json.loads(buf.getvalue().split("\n\n", 1)[0])
            self.assertGreaterEqual(payload["settled_this_cycle"], 1)
            self.assertEqual(payload["realized_pnl_cents"], -99)
            self.assertEqual(payload["model_version"], "exp-baseline-v1@2026-11-05")
            self.assertEqual(payload["software_version"], "2.1.0")
            self.assertEqual(payload["observed_at"], "2026-11-05T20:40:00Z")
            self.assertNotEqual(payload["observed_at"], "2026-11-05T19:45:00Z")
            self.assertFalse(Path("/workspace/personal-finance/kalshi-paper/state/ledger.sqlite").exists())

    def test_public_client_rejects_order_paths(self):
        client = PublicClient("https://api.elections.kalshi.com/trade-api/v2")
        with self.assertRaises(RuntimeError):
            client.get_json("/portfolio/orders")

    def test_public_client_maps_http_errors(self):
        class Boom:
            def __enter__(self):
                raise FeedError("boom", status=403)

            def __exit__(self, *args):
                return False

        client = PublicClient("https://example.invalid/trade-api/v2")
        with patch("kxbtc15m.client.urllib.request.urlopen", side_effect=FeedError("403 unknown", status=403)):
            with self.assertRaises(FeedError) as ctx:
                client.get_json("/series/KXBTC15M")
            self.assertEqual(ctx.exception.status, 403)


if __name__ == "__main__":
    unittest.main()
