import unittest
from datetime import datetime, timedelta, timezone

from rera_tracker import tokens
from rera_tracker.clock import IST, today_ist, utc_stamp

SECRET = "a-long-random-test-secret-0123456789"


class TokensTest(unittest.TestCase):
    def test_round_trip(self):
        token = tokens.sign(SECRET, "unsub", "42")
        self.assertEqual(tokens.verify(SECRET, "unsub", token), "42")

    def test_links_survive_being_pasted_into_a_url(self):
        token = tokens.sign(SECRET, "confirm", "7", expires_at=2_000_000_000)
        self.assertRegex(token, r"^[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+$")

    def test_wrong_secret_wrong_purpose_and_tampering_are_refused(self):
        token = tokens.sign(SECRET, "unsub", "42")
        for bad in (
            lambda: tokens.verify("another-secret-another-secret", "unsub", token),
            lambda: tokens.verify(SECRET, "confirm", token),
            lambda: tokens.verify(SECRET, "unsub", token[:-2] + ("AA" if not token.endswith("AA") else "BB")),
            lambda: tokens.verify(SECRET, "unsub", token.replace("A", "B", 1) if "A" in token else token + "x"),
        ):
            with self.assertRaises(tokens.TokenError):
                bad()

    def test_malformed_input_never_crashes(self):
        for junk in ("", "x", "a.b", "....", "💥", "a.b.c", "YQ.YQ", None):
            with self.assertRaises(tokens.TokenError):
                tokens.verify(SECRET, "unsub", junk)

    def test_expiry(self):
        token = tokens.sign(SECRET, "confirm", "7", expires_at=1000)
        self.assertEqual(tokens.verify(SECRET, "confirm", token, now=999), "7")
        self.assertEqual(tokens.verify(SECRET, "confirm", token, now=1000), "7")
        with self.assertRaises(tokens.TokenError):
            tokens.verify(SECRET, "confirm", token, now=1001)

    def test_a_token_without_expiry_never_expires(self):
        token = tokens.sign(SECRET, "unsub", "1")
        self.assertEqual(tokens.verify(SECRET, "unsub", token, now=10 ** 12), "1")

    def test_refuses_to_sign_with_no_secret_or_with_separators(self):
        with self.assertRaises(ValueError):
            tokens.sign("", "unsub", "1")
        with self.assertRaises(ValueError):
            tokens.sign(SECRET, "un|sub", "1")
        with self.assertRaises(ValueError):
            tokens.sign(SECRET, "unsub", "1|2")
        with self.assertRaises(tokens.TokenError):
            tokens.verify("", "unsub", tokens.sign(SECRET, "unsub", "1"))


class ClockTest(unittest.TestCase):
    def test_india_date_differs_from_utc_date_in_the_small_hours(self):
        utc_evening = datetime(2026, 11, 18, 20, 0, tzinfo=timezone.utc)  # 01:30 on the 19th in India
        self.assertEqual(today_ist(utc_evening).isoformat(), "2026-11-19")
        self.assertEqual(today_ist(datetime(2026, 11, 18, 10, 0, tzinfo=timezone.utc)).isoformat(), "2026-11-18")
        self.assertEqual(today_ist(datetime(2026, 11, 18, 18, 29, tzinfo=timezone.utc)).isoformat(), "2026-11-18")
        self.assertEqual(today_ist(datetime(2026, 11, 18, 18, 30, tzinfo=timezone.utc)).isoformat(), "2026-11-19")
        self.assertEqual(IST.utcoffset(None), timedelta(hours=5, minutes=30))

    def test_utc_stamp(self):
        self.assertEqual(utc_stamp(0), "1970-01-01T00:00:00Z")
        self.assertEqual(utc_stamp(1795082400), "2026-11-19T10:00:00Z")


if __name__ == "__main__":
    unittest.main()
