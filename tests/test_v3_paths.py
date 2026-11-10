import tempfile
from pathlib import Path

from kxbtc15m.v3.paths import assert_safe_v3_dir, V3Error


def test_refuses_baseline_and_openexit():
    for p in (
        "/workspace/personal-finance/kalshi-paper/state",
        "/workspace/var/openexit",
    ):
        try:
            assert_safe_v3_dir(p)
            raise AssertionError("should have refused")
        except V3Error:
            pass


def test_allows_isolated_temp():
    with tempfile.TemporaryDirectory() as raw:
        got = assert_safe_v3_dir(Path(raw) / "v3")
        assert got.name == "v3"
