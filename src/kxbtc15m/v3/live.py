"""v3-live: refresh preview/results on a loop and serve the state dir locally."""

from __future__ import annotations

import json
import signal
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from kxbtc15m.config import DEFAULT_API_BASE
from kxbtc15m.v3.paths import assert_safe_v3_dir
from kxbtc15m.v3.pipeline import run_preview
from kxbtc15m.v3.screen import write_screen

DEFAULT_INTERVAL = 20
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 43147


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A003
        return


def _mark_stale(state_dir: Path, reason: str) -> None:
    path = state_dir / "preview.json"
    payload: dict = {}
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
    payload["stale"] = True
    payload["stale_reason"] = str(reason)[:500]
    payload["stale_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    try:
        write_screen(state_dir)
    except Exception:
        pass


def refresh_once(state_dir: Path, api_base: str) -> dict:
    return run_preview(state_dir, api_base)


def run_live(
    state_dir: Path | str,
    api_base: str = DEFAULT_API_BASE,
    interval: int = DEFAULT_INTERVAL,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> int:
    state_dir = assert_safe_v3_dir(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    interval = max(5, int(interval))
    stop = {"flag": False}

    def _stop(signum=None, frame=None):
        stop["flag"] = True

    try:
        signal.signal(signal.SIGINT, _stop)
    except Exception:
        pass
    try:
        signal.signal(signal.SIGTERM, _stop)
    except Exception:
        pass

    handler = partial(_QuietHandler, directory=str(state_dir))
    server = ThreadingHTTPServer((host, int(port)), handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    sys.stdout.write(f"v3-live serving http://{host}:{port}/results.html  interval={interval}s\n")
    sys.stdout.flush()
    try:
        while not stop["flag"]:
            started = time.time()
            try:
                bundle = refresh_once(state_dir, api_base)
                cur = (bundle.get("current") or {}).get("ticker")
                nxt = (bundle.get("next") or {}).get("ticker")
                sys.stdout.write(
                    f"{bundle.get('run_generated_at')} current={cur} next={nxt} stale=false\n"
                )
            except Exception as exc:
                sys.stdout.write(f"{datetime.now(timezone.utc).isoformat()} error={exc}\n")
                traceback.print_exc(file=sys.stdout)
                try:
                    _mark_stale(state_dir, str(exc))
                except Exception:
                    pass
            sys.stdout.flush()
            elapsed = time.time() - started
            remaining = max(0.0, float(interval) - elapsed)
            end = time.time() + remaining
            while time.time() < end and not stop["flag"]:
                time.sleep(min(0.5, end - time.time()))
    finally:
        server.shutdown()
        server.server_close()
    return 0
