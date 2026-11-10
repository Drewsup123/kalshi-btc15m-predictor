"""Public GET-only client. Order and auth paths are disabled."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

FORBIDDEN_FRAGMENTS = (
    "/portfolio",
    "/orders",
    "/order_groups",
    "/api_keys",
    "/cfbenchmarks",
    "/fills",
    "/communications",
)


class FeedError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class PublicGetClient:
    def __init__(self, timeout: float = 20.0, retries: int = 4, user_agent: str = "kxbtc15m-v3/1.0 (personal; GET only; no orders)"):
        self.timeout = timeout
        self.retries = retries
        self.user_agent = user_agent

    def get_json(self, url: str) -> Any:
        lowered = url.lower()
        if any(fragment in lowered for fragment in FORBIDDEN_FRAGMENTS):
            raise RuntimeError("order/auth paths are disabled in V3 (read-only public GET)")
        request = urllib.request.Request(
            url,
            method="GET",
            headers={"Accept": "application/json", "User-Agent": self.user_agent},
        )
        last: FeedError | None = None
        for attempt in range(self.retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read()
                    return json.loads(raw.decode("utf-8"))
            except urllib.error.HTTPError as exc:
                last = FeedError(f"HTTP {exc.code} for {url}", status=exc.code)
                if exc.code not in {429, 500, 502, 503, 504} or attempt == self.retries:
                    raise last from exc
            except urllib.error.URLError as exc:
                last = FeedError(f"feed error for {url}: {exc.reason}")
                if attempt == self.retries:
                    raise last from exc
            time.sleep(min(32.0, 0.5 * (2 ** attempt)))
        raise last or FeedError(url)

    def kalshi(self, api_base: str, path: str, query: dict | None = None) -> dict:
        if not path.startswith("/"):
            raise RuntimeError("path must start with /")
        url = api_base.rstrip("/") + path
        if query:
            url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
        payload = self.get_json(url)
        if not isinstance(payload, dict):
            raise FeedError(f"unexpected JSON from {path}")
        return payload
