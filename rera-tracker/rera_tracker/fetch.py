"""A deliberately slow, identifiable HTTP client.

The tracker reads a public government website.  It must never look like, or
behave like, an attack: one request at a time, a pause between requests, a
User-Agent that says who is calling, and a hard cap on requests per run.
"""
from __future__ import annotations

import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Dict, Optional

DEFAULT_DELAY = 5.0
DEFAULT_TIMEOUT = 60.0


class FetchError(Exception):
    """A page could not be fetched."""


class RequestBudgetExceeded(FetchError):
    """The per-run request cap was reached."""


def default_user_agent() -> str:
    contact = os.environ.get("RERA_TRACKER_CONTACT", "").strip() or "contact not configured"
    return "rera-tracker/0.1 (reads public RERA records; %s)" % contact


class PoliteFetcher:
    def __init__(
        self,
        min_delay: float = DEFAULT_DELAY,
        timeout: float = DEFAULT_TIMEOUT,
        retries: int = 2,
        user_agent: Optional[str] = None,
        cafile: Optional[str] = None,
        max_requests: Optional[int] = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.min_delay = max(0.0, min_delay)
        self.timeout = timeout
        self.retries = max(0, retries)
        self.user_agent = user_agent or default_user_agent()
        self.max_requests = max_requests
        self.requests_made = 0
        self._sleep = sleep
        self._clock = clock
        self._last_request: Optional[float] = None
        cafile = cafile or os.environ.get("RERA_TRACKER_CA_BUNDLE") or None
        context = ssl.create_default_context(cafile=cafile)
        self._opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context))

    def get(self, url: str) -> str:
        return self._request(url, None)

    def post(self, url: str, fields: Dict[str, str]) -> str:
        return self._request(url, urllib.parse.urlencode(fields).encode("ascii"))

    # ------------------------------------------------------------------
    def _wait(self) -> None:
        if self._last_request is not None:
            remaining = self.min_delay - (self._clock() - self._last_request)
            if remaining > 0:
                self._sleep(remaining)

    def _request(self, url: str, body: Optional[bytes]) -> str:
        if urllib.parse.urlparse(url).scheme != "https":
            raise FetchError("only https URLs are fetched: %r" % url)
        last_error: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            if self.max_requests is not None and self.requests_made >= self.max_requests:
                raise RequestBudgetExceeded("request cap of %d reached" % self.max_requests)
            self._wait()
            if attempt:
                self._sleep(self.min_delay * attempt)
            request = urllib.request.Request(
                url,
                data=body,
                headers={"User-Agent": self.user_agent, "Accept": "text/html,application/xhtml+xml"},
            )
            self.requests_made += 1
            try:
                with self._opener.open(request, timeout=self.timeout) as response:
                    raw = response.read()
                self._last_request = self._clock()
                return raw.decode("utf-8", "replace")
            except urllib.error.HTTPError as error:
                self._last_request = self._clock()
                last_error = error
                if error.code < 500:
                    raise FetchError("HTTP %d for %s" % (error.code, url)) from error
            except (urllib.error.URLError, TimeoutError, ConnectionError, ssl.SSLError) as error:
                self._last_request = self._clock()
                last_error = error
        raise FetchError("could not fetch %s: %s" % (url, last_error))
