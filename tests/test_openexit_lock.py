import tempfile
import unittest
from pathlib import Path

from kxbtc15m.openexit.lock import WatchLock


class LockTests(unittest.TestCase):
    def test_second_watch_fails(self):
        with tempfile.TemporaryDirectory() as raw:
            state = Path(raw)
            a = WatchLock(state)
            b = WatchLock(state)
            a.acquire()
            with self.assertRaises(RuntimeError):
                b.acquire()
            a.release()
            b.acquire()
            b.release()


if __name__ == "__main__":
    unittest.main()
