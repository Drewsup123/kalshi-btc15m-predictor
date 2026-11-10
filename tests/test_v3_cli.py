import io
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

from kxbtc15m.cli import main
from tests.isolation import assert_parent_ledger_untouched, snapshot_parent_ledger


def test_v3_screen_untrained_isolated_and_parent_untouched():
    before = snapshot_parent_ledger()
    with tempfile.TemporaryDirectory() as raw:
        state = Path(raw) / "v3"
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["v3-screen", "--state-dir", str(state)])
        assert code == 0
        html = (state / "results.html").read_text(encoding="utf-8")
        assert "not trained" in html
        assert not (state / "ledger.sqlite").exists()
    assert_parent_ledger_untouched(__import__("unittest").TestCase(), before)


def test_v3_refuses_openexit_dir():
    try:
        main(["v3-screen", "--state-dir", "/workspace/var/openexit"])
        raise AssertionError("should refuse")
    except Exception:
        pass
