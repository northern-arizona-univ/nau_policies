"""Polite HTTP fetching with retries and an in-run cache."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import requests


@dataclass
class Result:
    url: str
    status: Optional[int]
    final_url: str
    content: bytes
    content_type: str = ""
    encoding: Optional[str] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 300

    @property
    def text(self) -> str:
        return self.content.decode(self.encoding or "utf-8", errors="replace")


class Fetcher:
    def __init__(self, user_agent: str, delay: float = 1.0, timeout: float = 45, retries: int = 3):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self.delay = delay
        self.timeout = timeout
        self.retries = retries
        self._last = 0.0
        self.cache: Dict[str, Result] = {}
        self.log: List[dict] = []

    def _wait(self) -> None:
        gap = self.delay - (time.time() - self._last)
        if gap > 0:
            time.sleep(gap)

    def get(self, url: str, max_bytes: Optional[int] = None) -> Result:
        if url in self.cache:
            return self.cache[url]
        result: Optional[Result] = None
        for attempt in range(self.retries):
            self._wait()
            try:
                r = self.session.get(url, timeout=self.timeout, allow_redirects=True, stream=max_bytes is not None)
                self._last = time.time()
                if r.status_code == 429 or r.status_code >= 500:
                    raise requests.HTTPError(f"HTTP {r.status_code}")
                if max_bytes is not None:
                    declared = int(r.headers.get("content-length") or 0)
                    if declared > max_bytes:
                        r.close()
                        result = Result(url, r.status_code, r.url, b"", r.headers.get("content-type", ""),
                                        error=f"skipped: {declared} bytes exceeds limit")
                        break
                    content = r.content
                else:
                    content = r.content
                result = Result(url, r.status_code, r.url, content, r.headers.get("content-type", ""),
                                encoding=r.encoding if not max_bytes else None)
                if result.encoding is None and "html" in result.content_type:
                    result.encoding = r.apparent_encoding or "utf-8"
                break
            except requests.RequestException as e:
                self._last = time.time()
                if attempt == self.retries - 1:
                    result = Result(url, None, url, b"", error=str(e))
                else:
                    time.sleep(2 ** (attempt + 1))
        assert result is not None
        self.cache[url] = result
        self.log.append({"url": url, "status": result.status, "bytes": len(result.content), "error": result.error})
        return result
