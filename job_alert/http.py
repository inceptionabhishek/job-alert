from __future__ import annotations

import json
import logging
import re
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


def redact(value: object) -> str:
    return re.sub(r"(api\.telegram\.org/bot)[^/\s]+", r"\1[REDACTED]", str(value))


class HttpClient:
    def __init__(self, config: dict[str, Any] | None = None):
        config = config or {}
        self.timeout = float(config.get("timeout_seconds", 20))
        self.retries = int(config.get("retries", 2))
        self.backoff = float(config.get("retry_backoff_seconds", 1))
        self.user_agent = str(config.get("user_agent", "PersonalJobAlert/0.1"))

    def request(self, url: str, *, data: bytes | None = None, headers: dict[str, str] | None = None) -> bytes:
        merged = {"User-Agent": self.user_agent, "Accept": "application/json,text/html;q=0.9,*/*;q=0.8"}
        merged.update(headers or {})
        request = Request(url, data=data, headers=merged, method="POST" if data is not None else "GET")
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    return response.read()
            except (HTTPError, URLError, TimeoutError) as exc:
                last_error = exc
                if attempt >= self.retries:
                    break
                delay = self.backoff * (2**attempt)
                logger.warning("Request failed for %s; retrying in %.1fs (%s)", redact(url), delay, redact(exc))
                time.sleep(delay)
        raise RuntimeError(f"Request failed after {self.retries + 1} attempts: {redact(url)}: {redact(last_error)}") from None

    def get_json(self, url: str) -> Any:
        return json.loads(self.request(url).decode("utf-8"))

    def get_text(self, url: str) -> str:
        return self.request(url).decode("utf-8", errors="replace")
