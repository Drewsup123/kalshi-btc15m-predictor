import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from kxbtc15m.cli import main
from tests.test_openexit_tick import Fake, _book, _hist, _open


NOW = datetime(2026, 11, 5, 19, 31, 0, tzinfo=timezone.utc)
PARENT = Path("/workspace/personal-finance/kalshi-paper/state/ledger.sqlite")


class OpenExitCliTests(unittest.TestCase):
    def test_run_uses_isolated_ledger_not_parent(self):
        with tempfile.TemporaryDirectory() as raw:
            state = Path(raw)
            buf = io.StringIO()
            with (
                redirect_stdout(buf),
                patch("kxbtc15m.cli.PublicClient", return_value=Fake({"settled": _hist(), "open": _open(), "book": _book()})),
                patch("kxbtc15m.cli.utc_now", return_value=NOW),
            ):
                code = main(["run", "--state-dir", str(state)])
            self.assertEqual(code, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["action"], "entry")
            self.assertTrue((state / "openexit.sqlite").exists())
            self.assertFalse((state / "ledger.sqlite").exists())
            self.assertFalse(PARENT.exists())

    def test_run_refuses_parent_state_dir(self):
        with self.assertRaises(RuntimeError):
            main(["run", "--state-dir", "/workspace/personal-finance/kalshi-paper/state"])
        self.assertFalse(PARENT.exists())


if __name__ == "__main__":
    unittest.main()
