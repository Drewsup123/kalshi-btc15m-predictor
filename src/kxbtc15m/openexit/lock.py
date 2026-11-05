"""Singleton lock for the 20s watch process."""

from __future__ import annotations

import os
from pathlib import Path

from kxbtc15m.openexit.paths import assert_safe_openexit_dir


class WatchLock:
    def __init__(self, state_dir: Path):
        self.state_dir = assert_safe_openexit_dir(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.state_dir / "watch.lock"
        self.pid_path = self.state_dir / "watch.pid"
        self._fh = None

    def acquire(self) -> None:
        self._fh = open(self.path, "a+")
        try:
            import fcntl

            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._fh.close()
            self._fh = None
            raise RuntimeError(f"watch already running (lock {self.path})") from exc
        self._fh.seek(0)
        self._fh.truncate()
        self._fh.write(str(os.getpid()))
        self._fh.flush()
        self.pid_path.write_text(str(os.getpid()), encoding="utf-8")

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            import fcntl

            fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        finally:
            self._fh.close()
            self._fh = None
            try:
                self.pid_path.unlink(missing_ok=True)
            except OSError:
                pass
