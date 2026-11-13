import unittest
import urllib.error
from unittest import mock

from rera_tracker import fetch
from rera_tracker.fetch import FetchError, PoliteFetcher, RequestBudgetExceeded


class FakeResponse:
    def __init__(self, body=b"ok"):
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Harness:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.requests = []
        self.sleeps = []
        self.now = 0.0

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(round(seconds, 3))
        self.now += seconds

    def opener_open(self, request, timeout=None):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(outcome)

    def fetcher(self, **kwargs):
        instance = PoliteFetcher(sleep=self.sleep, clock=self.clock, **kwargs)
        instance._opener = mock.Mock()
        instance._opener.open.side_effect = self.opener_open
        return instance


def http_error(code):
    return urllib.error.HTTPError("https://x.example/", code, "err", {}, None)


class PoliteFetcherTest(unittest.TestCase):
    def test_get_returns_text_and_identifies_itself(self):
        h = Harness([b"hello \xe0\xa4\xb9"])
        page = h.fetcher(user_agent="rera-tracker/0.1 (test)").get("https://haryanarera.gov.in/x")
        self.assertEqual(page, "hello ह")
        request = h.requests[0]
        self.assertEqual(request.get_header("User-agent"), "rera-tracker/0.1 (test)")
        self.assertIsNone(request.data)

    def test_default_user_agent_carries_the_contact_address(self):
        with mock.patch.dict("os.environ", {"RERA_TRACKER_CONTACT": "ops@example.com"}):
            self.assertIn("ops@example.com", fetch.default_user_agent())
        with mock.patch.dict("os.environ", {"RERA_TRACKER_CONTACT": ""}):
            self.assertIn("contact not configured", fetch.default_user_agent())

    def test_post_sends_form_fields(self):
        h = Harness([b"ok"])
        h.fetcher().post("https://haryanarera.gov.in/x", {"a": "1", "b": "two words"})
        self.assertEqual(h.requests[0].data, b"a=1&b=two+words")

    def test_requests_are_spaced_out(self):
        h = Harness([b"1", b"2", b"3"])
        f = h.fetcher(min_delay=5)
        for _ in range(3):
            f.get("https://haryanarera.gov.in/x")
        self.assertEqual(h.sleeps, [5.0, 5.0])

    def test_server_errors_are_retried_with_a_growing_pause(self):
        h = Harness([http_error(503), http_error(502), b"finally"])
        f = h.fetcher(min_delay=2, retries=2)
        self.assertEqual(f.get("https://haryanarera.gov.in/x"), "finally")
        self.assertEqual(f.requests_made, 3)
        self.assertEqual(h.sleeps, [2.0, 2.0, 2.0, 4.0])

    def test_client_errors_are_not_retried(self):
        h = Harness([http_error(404), b"unused"])
        f = h.fetcher(retries=2)
        with self.assertRaises(FetchError) as caught:
            f.get("https://haryanarera.gov.in/x")
        self.assertIn("HTTP 404", str(caught.exception))
        self.assertEqual(f.requests_made, 1)

    def test_giving_up_after_the_retries(self):
        h = Harness([urllib.error.URLError("boom")] * 3)
        f = h.fetcher(min_delay=1, retries=2)
        with self.assertRaises(FetchError):
            f.get("https://haryanarera.gov.in/x")
        self.assertEqual(f.requests_made, 3)

    def test_request_cap(self):
        h = Harness([b"1", b"2", b"3"])
        f = h.fetcher(max_requests=2)
        f.get("https://haryanarera.gov.in/a")
        f.get("https://haryanarera.gov.in/b")
        with self.assertRaises(RequestBudgetExceeded):
            f.get("https://haryanarera.gov.in/c")
        self.assertEqual(len(h.requests), 2)

    def test_only_https(self):
        h = Harness([b"x"])
        with self.assertRaises(FetchError):
            h.fetcher().get("http://haryanarera.gov.in/x")
        self.assertEqual(h.requests, [])


if __name__ == "__main__":
    unittest.main()
