"""Public production GET client. Order and account paths are disabled."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

FORBIDDEN_FRAGMENTS = ("/portfolio", "/orders", "/order_groups", "/api_keys")
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class FeedError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class PublicClient:
    def __init__(self, api_base: str, timeout: float = 15.0, retries: int = 2):
        self.api_base = api_base.rstrip("/")
        self.timeout = timeout
        self.retries = retries

    def get_json(self, path: str, query: dict[str, Any] | None = None) -> dict:
        if not path.startswith("/"):
            raise RuntimeError("path must start with /")
        lowered = path.lower()
        if any(fragment in lowered for fragment in FORBIDDEN_FRAGMENTS):
            raise RuntimeError("order/account paths are disabled in this paper simulator")
        url = self.api_base + path
        if query:
            url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Accept": "application/json",
                "User-Agent": "kxbtc15m-paper/1.0 (personal paper simulator; GET only)",
            },
        )
        last_error: FeedError | None = None
        attempts = self.retries + 1
        for attempt in range(attempts):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read()
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except json.JSONDecodeError as exc:
                        raise FeedError(f"malformed JSON from {path}: {exc}", status=response.status) from exc
                    if not isinstance(payload, dict):
                        raise FeedError(f"unexpected JSON type from {path}", status=response.status)
                    return payload
            except FeedError:
                raise
            except urllib.error.HTTPError as exc:
                last_error = FeedError(f"HTTP {exc.code} for {path}: {exc.reason}", status=exc.code)
                if exc.code not in RETRY_STATUSES or attempt == attempts - 1:
                    raise last_error from exc
            except urllib.error.URLError as exc:
                last_error = FeedError(f"feed error for {path}: {exc.reason}", status=None)
                if attempt == attempts - 1:
                    raise last_error from exc
            time.sleep(0.25 * (attempt + 1))
        raise last_error or FeedError(f"feed error for {path}")
