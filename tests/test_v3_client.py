from kxbtc15m.v3.client import PublicGetClient


def test_forbids_order_and_auth_paths():
    client = PublicGetClient()
    for url in (
        "https://api.elections.kalshi.com/trade-api/v2/portfolio/orders",
        "https://api.elections.kalshi.com/trade-api/v2/orders",
        "https://api.elections.kalshi.com/trade-api/v2/cfbenchmarks/values?id=BRTI",
        "https://api.elections.kalshi.com/trade-api/v2/api_keys",
    ):
        try:
            client.get_json(url)
            raise AssertionError(url)
        except RuntimeError as exc:
            assert "disabled" in str(exc).lower()
