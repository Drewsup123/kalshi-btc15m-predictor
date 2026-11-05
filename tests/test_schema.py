import unittest

from kxbtc15m.schema import unwrap_market, unwrap_markets


class SchemaTests(unittest.TestCase):
    def test_unwraps_official_market_envelope(self):
        inner = unwrap_market(
            {"market": {"ticker": "KXBTC15M-26NOV051445-45", "status": "finalized", "result": "yes"}}
        )
        self.assertEqual(inner["result"], "yes")
        self.assertEqual(inner["ticker"], "KXBTC15M-26NOV051445-45")

    def test_bare_market_passthrough(self):
        raw = {"ticker": "T", "status": "active", "result": ""}
        self.assertEqual(unwrap_market(raw)["ticker"], "T")

    def test_markets_list(self):
        payload = {"markets": [{"ticker": "A", "result": "no"}, {"ticker": "B", "result": "yes"}]}
        self.assertEqual(unwrap_market(payload)["ticker"], "A")
        self.assertEqual([m["ticker"] for m in unwrap_markets(payload)], ["A", "B"])

    def test_missing_payload(self):
        self.assertIsNone(unwrap_market(None))
        self.assertEqual(unwrap_markets({}), [])


if __name__ == "__main__":
    unittest.main()
