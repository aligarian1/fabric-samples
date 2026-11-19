import unittest

from rera_tracker.store import Store


def listed(n, name="TOWERS", authority="gurugram"):
    return {"key": "%s:ID-%d" % (authority, n), "authority": authority, "project_id": "ID-%d" % n, "name": name,
            "builder": "B", "location": "L", "district": "D"}


class SignupStoreTest(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)
        self.store.upsert_listed("gurugram", [listed(1), listed(2)], "2026-11-19T00:00:00Z")

    def follow(self, address, *keys):
        sid = self.store.add_subscriber("", "email", address, "en", "2026-11-19T00:00:00Z")
        for key in keys:
            self.store.subscribe(sid, key, "2026-11-19T00:00:00Z")
        return sid

    def test_signup_lifecycle(self):
        sid = self.store.create_signup("a@example.com", "hi", "gurugram:ID-1", "v1", "2026-11-19T10:00:00Z")
        signup = self.store.get_signup(sid)
        self.assertEqual((signup["email"], signup["lang"], signup["notice_version"], signup["confirmed_at"]),
                         ("a@example.com", "hi", "v1", None))
        self.store.confirm_signup(sid, 5, "2026-11-19T10:05:00Z")
        self.assertEqual(self.store.get_signup(sid)["subscriber_id"], 5)
        self.store.delete_signup(sid)
        self.assertIsNone(self.store.get_signup(sid))

    def test_counting_is_case_insensitive_and_windowed(self):
        self.store.create_signup("a@example.com", "en", "gurugram:ID-1", "v1", "2026-11-18T09:00:00Z")
        self.store.create_signup("A@Example.com", "en", "gurugram:ID-2", "v1", "2026-11-19T09:00:00Z")
        self.assertEqual(self.store.count_signups_since("a@example.com", "2026-11-19T00:00:00Z"), 1)
        self.assertEqual(self.store.count_signups_since("a@example.com", "2026-11-17T00:00:00Z"), 2)
        self.assertEqual(self.store.count_signups_since("b@example.com", "2026-11-17T00:00:00Z"), 0)
        first = self.store.create_signup("a@example.com", "en", "gurugram:ID-1", "v1", "2026-11-19T11:00:00Z")
        self.store.confirm_signup(first, 1, "2026-11-19T11:01:00Z")
        self.assertEqual(self.store.count_signups_since("a@example.com", "2026-11-19T00:00:00Z"), 2)
        self.assertEqual(self.store.count_signups_since("a@example.com", "2026-11-19T00:00:00Z", unconfirmed_only=True), 1)

    def test_only_unconfirmed_old_requests_are_purged(self):
        old = self.store.create_signup("a@example.com", "en", "gurugram:ID-1", "v1", "2026-11-01T00:00:00Z")
        kept = self.store.create_signup("b@example.com", "en", "gurugram:ID-1", "v1", "2026-11-19T00:00:00Z")
        confirmed = self.store.create_signup("c@example.com", "en", "gurugram:ID-1", "v1", "2026-11-01T00:00:00Z")
        self.store.confirm_signup(confirmed, 1, "2026-11-02T00:00:00Z")
        self.assertEqual(self.store.purge_unconfirmed("2026-11-12T00:00:00Z"), 1)
        self.assertIsNone(self.store.get_signup(old))
        self.assertIsNotNone(self.store.get_signup(kept))
        self.assertIsNotNone(self.store.get_signup(confirmed))

    def test_is_subscribed(self):
        self.follow("A@Example.com", "gurugram:ID-1")
        self.assertTrue(self.store.is_subscribed("email", "a@example.com", "gurugram:ID-1"))
        self.assertFalse(self.store.is_subscribed("email", "a@example.com", "gurugram:ID-2"))
        self.assertFalse(self.store.is_subscribed("whatsapp", "a@example.com", "gurugram:ID-1"))

    def test_stopping_the_last_project_erases_the_person(self):
        sid = self.follow("a@example.com", "gurugram:ID-1", "gurugram:ID-2")
        self.assertFalse(self.store.stop_project(sid, "gurugram:ID-1"))
        self.assertEqual(self.store.subscriptions_of(sid), ["gurugram:ID-2"])
        self.assertIsNotNone(self.store.get_subscriber_by_id(sid))
        self.assertTrue(self.store.stop_project(sid, "gurugram:ID-2"))
        self.assertIsNone(self.store.get_subscriber_by_id(sid))

    def test_erasure_removes_everything_about_the_person_and_nothing_else(self):
        mine = self.follow("a@example.com", "gurugram:ID-1")
        other = self.follow("b@example.com", "gurugram:ID-1")
        event = self.store.record_event("gurugram:ID-1", "baseline", "baseline", {}, "2026-11-19T00:00:00Z", False)
        self.store.queue_message(mine, event, "s", "b", "2026-11-19T00:00:00Z")
        self.store.queue_message(other, event, "s", "b", "2026-11-19T00:00:00Z")
        self.store.create_signup("a@example.com", "en", "gurugram:ID-1", "v1", "2026-11-19T00:00:00Z")
        keep = self.store.create_signup("b@example.com", "en", "gurugram:ID-1", "v1", "2026-11-19T00:00:00Z")
        self.assertTrue(self.store.delete_subscriber(mine))
        self.assertFalse(self.store.delete_subscriber(mine))
        self.assertIsNone(self.store.get_subscriber_by_id(mine))
        self.assertEqual(self.store.subscriptions_of(mine), [])
        self.assertEqual(self.store.count_signups_since("a@example.com", "2000-01-01T00:00:00Z"), 0)
        self.assertEqual([m["address"] for m in self.store.pending_messages()], ["b@example.com"])
        self.assertIsNotNone(self.store.get_signup(keep))
        self.assertIsNotNone(self.store.get_subscriber_by_id(other))

    def test_pending_messages_name_the_subscriber(self):
        sid = self.follow("a@example.com", "gurugram:ID-1")
        event = self.store.record_event("gurugram:ID-1", "baseline", "baseline", {}, "2026-11-19T00:00:00Z", False)
        self.store.queue_message(sid, event, "s", "b", "2026-11-19T00:00:00Z")
        self.assertEqual(self.store.pending_messages()[0]["subscriber_id"], sid)

    def test_search_treats_wildcards_as_plain_characters(self):
        self.store.upsert_listed("gurugram", [listed(3, "50% DONE_TOWERS"), listed(4, "OTHER")], "2026-11-19T00:00:00Z")
        names = lambda text: [p["name"] for p in self.store.find_projects(text)]  # noqa: E731
        self.assertEqual(names("%"), ["50% DONE_TOWERS"])
        self.assertEqual(names("_"), ["50% DONE_TOWERS"])
        self.assertEqual(names("done_t"), ["50% DONE_TOWERS"])
        self.assertEqual(names("zzz"), [])

    def test_website_numbers(self):
        self.assertEqual(self.store.count_projects(), 2)
        self.assertEqual(self.store.project_refs(), [("gurugram", "ID-1"), ("gurugram", "ID-2")])
        self.assertIsNone(self.store.last_sync())
        self.store.set_meta("synced:gurugram", "2026-11-18T01:00:00Z")
        self.store.set_meta("synced:panchkula", "2026-11-19T01:00:00Z")
        self.assertEqual(self.store.last_sync(), "2026-11-19T01:00:00Z")


if __name__ == "__main__":
    unittest.main()
