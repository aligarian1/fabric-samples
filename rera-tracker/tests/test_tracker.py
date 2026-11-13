import os
import tempfile
import unittest
from datetime import date

from rera_tracker.fetch import FetchError
from rera_tracker.haryana import HaryanaSource, ParseError
from rera_tracker.store import Store
from rera_tracker.tracker import Tracker, build_state

from . import fixtures as fx

LIST_URL = "https://haryanarera.gov.in/admincontrol/registered_projects/2"
DETAIL = fx.detail_url(9001)
SCHEDULE = fx.qpr_url("OTAwMQ==")
REPORT = "https://haryanarera.gov.in/view_project/quaterly_schedule_preview_open"


class FakeSite:
    """Stands in for the fetcher: serves pages by URL and records every request."""

    def __init__(self):
        self.pages = {}
        self.broken = set()
        self.calls = []

    def _serve(self, url, fields=None):
        self.calls.append((url, dict(fields) if fields else None))
        if url in self.broken:
            raise FetchError("simulated outage for %s" % url)
        key = (url, fields["quarter_no"] + "/" + fields["quarter_year"]) if fields else url
        if key not in self.pages:
            raise FetchError("HTTP 404 for %s" % url)
        return self.pages[key]

    def get(self, url):
        return self._serve(url)

    def post(self, url, fields):
        return self._serve(url, fields)

    def set_list(self, rows):
        self.pages[LIST_URL] = fx.list_page(rows)

    def set_report(self, number, year, html):
        self.pages[(REPORT, "%d/%d" % (number, year))] = html


def listing(valid="2027-06-30", lapsed=False, occ=False, with_qpr=True):
    day, month, year = valid[8:], valid[5:7], valid[:4]
    return fx.list_row(
        1, "RERA-GRG-9001-2024", "SUNRISE HEIGHTS", "EXAMPLE BUILDERS PVT LTD", "%s/%s/%s" % (day, month, year),
        site_id=9001, qpr_token="OTAwMQ==" if with_qpr else None, lapsed=lapsed, occ=occ,
    )


QUARTERS_TO_Q3 = [(2, 2026, "01-Apr-2026", "30-Jun-2026"), (3, 2026, "01-Jul-2026", "30-Sep-2026")]
QUARTERS_TO_Q4 = QUARTERS_TO_Q3 + [(4, 2026, "01-Oct-2026", "31-Dec-2026")]
HEARING = {"date": "21-Apr-2025", "text": "Approved.", "status": "APPROVED", "order": "NjE2Mw=="}


class Clock:
    def __init__(self):
        self.value = 0

    def __call__(self):
        self.value += 1
        return "2026-11-13T00:00:%02dZ" % (self.value % 60)


class TrackerFlowTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.store = Store(os.path.join(self.dir.name, "t.db"))
        self.addCleanup(self.store.close)
        self.site = FakeSite()
        self.site.set_list([listing()])
        self.site.pages[DETAIL] = fx.detail_page("APPROVED AND CERTIFICATE UPLOADED", "NOT REQUIRED", [HEARING])
        self.site.pages[SCHEDULE] = fx.schedule_page(QUARTERS_TO_Q3)
        self.site.set_report(3, 2026, fx.report_page(submitted="15-Oct-2026", collected=1741.3))
        self.clock = Clock()
        self.key = "gurugram:RERA-GRG-9001-2024"

    def tracker(self, today):
        return Tracker(self.store, HaryanaSource(self.site), today=today, now=self.clock)

    def start(self, today=date(2026, 11, 13), lang="en", channel="console", address="anita@example.com"):
        tracker = self.tracker(today)
        tracker.sync("gurugram")
        tracker.subscribe(self.key, "Anita", channel, address, lang)
        return tracker

    def messages(self):
        return self.store.pending_messages()

    # -- the happy path -------------------------------------------------------
    def test_sync_stores_the_list(self):
        counts = self.tracker(date(2026, 11, 13)).sync("gurugram")
        self.assertEqual(counts, {"new": 1, "total": 1, "dropped": 0})
        self.assertEqual(self.store.find_projects("sunrise")[0]["project_id"], "RERA-GRG-9001-2024")
        self.assertEqual(self.store.resolve("rera-grg-9001-2024")[0]["key"], self.key)

    def test_first_check_sends_one_baseline_report(self):
        tracker = self.start()
        result = tracker.check(self.key)
        self.assertEqual([e.kind for e in result["events"]], ["baseline"])
        self.assertEqual(result["queued"], 1)
        self.assertEqual(result["problems"], [])
        message = self.messages()[0]
        self.assertIn("Tracking started", message["subject"])
        self.assertIn("Latest report: Jul–Sep 2026, filed on 15 Oct 2026", message["body"])
        self.assertIn("₹17.41 crore", message["body"])

    def test_nothing_changed_means_nothing_sent_and_no_extra_requests_for_the_report(self):
        tracker = self.start()
        tracker.check(self.key)
        report_requests = [c for c in self.site.calls if c[1]]
        self.assertEqual(len(report_requests), 1)
        again = tracker.check(self.key)
        self.assertEqual(again["events"], [])
        self.assertEqual(again["queued"], 0)
        self.assertEqual(len([c for c in self.site.calls if c[1]]), 1, "the known report must not be downloaded again")
        self.assertEqual(len(self.messages()), 1)

    def test_a_new_quarterly_report_is_announced_once(self):
        tracker = self.start()
        tracker.check(self.key)
        self.site.pages[SCHEDULE] = fx.schedule_page(QUARTERS_TO_Q4)
        self.site.set_report(4, 2026, fx.report_page(submitted="14-Jan-2027", collected=900.0))
        later = self.tracker(date(2027, 1, 20))
        result = later.check(self.key)
        self.assertEqual([e.kind for e in result["events"]], ["new_report"])
        newest = self.messages()[-1]
        self.assertIn("The builder filed the report for Oct–Dec 2026 on 14 Jan 2027.", newest["body"])
        self.assertIn("(previous report: ₹17.41 crore)", newest["body"])
        self.assertEqual(later.check(self.key)["events"], [])
        self.assertEqual(len(self.messages()), 2)

    def test_registration_ending_soon_is_announced_once_per_threshold(self):
        self.site.set_list([listing(valid="2027-01-15")])
        tracker = self.start(today=date(2026, 11, 13))
        first = tracker.check(self.key)
        self.assertEqual([(e.kind, e.silent) for e in first["events"]], [("baseline", False), ("registration_expiring", True)])
        self.assertEqual(len(self.messages()), 1, "a warning that is already true on day one is noted, not announced")
        self.assertEqual(self.tracker(date(2026, 11, 14)).check(self.key)["events"], [])
        thirty = self.tracker(date(2026, 12, 20)).check(self.key)
        self.assertEqual([e.key for e in thirty["events"]], ["expiring:30:2027-01-15"])
        self.assertEqual(len(self.messages()), 2)
        self.assertIn("is 26 days away", self.messages()[-1]["body"])
        self.assertEqual(self.tracker(date(2026, 12, 21)).check(self.key)["events"], [])

    def test_overdue_report_is_announced_once(self):
        self.site.pages[SCHEDULE] = fx.schedule_page(QUARTERS_TO_Q3[:1])
        self.site.set_report(2, 2026, fx.report_page(submitted="12-Jul-2026"))
        tracker = self.start(today=date(2026, 10, 5))
        first = tracker.check(self.key)
        # Quarter 3 ended only 5 days earlier, so its report is not late yet.
        self.assertEqual([e.kind for e in first["events"]], ["baseline"])
        late = self.tracker(date(2026, 11, 13))
        result = late.check(self.key)
        self.assertEqual([e.kind for e in result["events"]], ["report_overdue"])
        self.assertEqual(result["events"][0].key, "overdue:2026Q3")
        self.assertIn("No quarterly report for the quarter that ended on 30 Sep 2026", self.messages()[-1]["body"])
        self.assertIn("The latest report on record is for Apr–Jun 2026.", self.messages()[-1]["body"])
        self.assertEqual(late.check(self.key)["events"], [])
        self.assertEqual(len(self.messages()), 2)

    def test_parts_read_for_the_first_time_after_an_outage_are_not_announced_as_news(self):
        self.site.broken.update({DETAIL, SCHEDULE})
        tracker = self.start()
        first = tracker.check(self.key)
        self.assertEqual([e.kind for e in first["events"]], ["baseline"])
        self.assertEqual(len(first["problems"]), 2)
        self.site.broken.clear()
        second = tracker.check(self.key)
        self.assertEqual(second["events"], [], "an old report and old hearings are not news")
        self.assertEqual(len(self.messages()), 1)
        self.assertEqual(len(self.store.get_project(self.key)["state"]["quarters"]), 2)
        # From here on, real changes are announced as usual.
        self.site.pages[SCHEDULE] = fx.schedule_page(QUARTERS_TO_Q4)
        self.site.set_report(4, 2026, fx.report_page(submitted="14-Jan-2027"))
        self.assertEqual([e.kind for e in self.tracker(date(2027, 1, 20)).check(self.key)["events"]], ["new_report"])

    def test_listing_changes_are_announced(self):
        tracker = self.start()
        tracker.check(self.key)
        self.site.set_list([listing(valid="2028-06-30", lapsed=False, occ=True)])
        tracker.sync("gurugram")
        result = tracker.check(self.key)
        self.assertEqual(sorted(e.kind for e in result["events"]), ["occ_uploaded", "validity_extended"])

    def test_the_project_disappearing_from_the_list(self):
        tracker = self.start()
        tracker.check(self.key)
        self.site.set_list([fx.list_row(2, "RERA-GRG-1-2020", "OTHER", "OTHER BUILDER", "01/01/2030", site_id=1)])
        counts = tracker.sync("gurugram")
        self.assertEqual((counts["new"], counts["dropped"]), (1, 1))
        result = tracker.check(self.key)
        self.assertEqual([e.kind for e in result["events"]], ["removed_from_list"])

    # -- failures must never look like news -----------------------------------
    def test_outage_keeps_the_old_state_and_sends_nothing(self):
        tracker = self.start()
        tracker.check(self.key)
        before = self.store.get_project(self.key)["state"]
        self.site.broken.update({DETAIL, SCHEDULE})
        result = tracker.check(self.key)
        self.assertEqual(result["events"], [])
        self.assertEqual(len(result["problems"]), 2)
        self.assertEqual(self.store.get_project(self.key)["state"], before)
        self.site.broken.clear()
        self.assertEqual(tracker.check(self.key)["events"], [])

    def test_a_report_that_cannot_be_read_is_retried_not_announced_without_figures(self):
        tracker = self.start()
        tracker.check(self.key)
        self.site.pages[SCHEDULE] = fx.schedule_page(QUARTERS_TO_Q4)
        self.site.broken.add(REPORT)
        later = self.tracker(date(2027, 1, 20))
        failed = later.check(self.key)
        self.assertEqual([e.kind for e in failed["events"]], [])
        self.assertTrue(any("quarterly reports" in p for p in failed["problems"]))
        self.site.broken.clear()
        self.site.set_report(4, 2026, fx.report_page(submitted="14-Jan-2027", collected=900.0))
        recovered = later.check(self.key)
        self.assertEqual([e.kind for e in recovered["events"]], ["new_report"])
        self.assertIn("₹9.00 crore", self.messages()[-1]["body"])

    def test_a_changed_page_layout_is_a_problem_not_a_change(self):
        tracker = self.start()
        tracker.check(self.key)
        self.site.pages[DETAIL] = "<html><body>We have moved. Please visit our new portal.</body></html>"
        result = tracker.check(self.key)
        self.assertEqual(result["events"], [])
        self.assertTrue(any("details page" in p for p in result["problems"]))

    def test_an_empty_list_never_wipes_the_stored_one(self):
        tracker = self.start()
        self.site.pages[LIST_URL] = fx.list_page([])
        with self.assertRaises(ParseError):
            tracker.sync("gurugram")
        self.assertEqual(len(self.store.all_listed("gurugram")), 1)
        self.site.pages[LIST_URL] = "<html><body>Down for maintenance</body></html>"
        with self.assertRaises(ParseError):
            tracker.sync("gurugram")
        with self.assertRaises(ValueError):
            tracker.sync("mumbai")

    # -- people ---------------------------------------------------------------
    def test_a_second_subscriber_gets_the_current_status_and_both_get_future_alerts(self):
        tracker = self.start()
        tracker.check(self.key)
        tracker.subscribe(self.key, "Ravi", "console", "ravi@example.com", "hi")
        waiting = [m for m in self.messages() if m["address"] == "ravi@example.com"]
        self.assertEqual(len(waiting), 1)
        self.assertIn("ट्रैकिंग शुरू", waiting[0]["subject"])
        self.site.pages[SCHEDULE] = fx.schedule_page(QUARTERS_TO_Q4)
        self.site.set_report(4, 2026, fx.report_page(submitted="14-Jan-2027"))
        self.tracker(date(2027, 1, 20)).check(self.key)
        for address in ("anita@example.com", "ravi@example.com"):
            self.assertEqual(len([m for m in self.messages() if m["address"] == address]), 2, address)
        hindi = [m for m in self.messages() if m["address"] == "ravi@example.com"][-1]
        self.assertIn("नई तिमाही रिपोर्ट दाखिल", hindi["subject"])

    def test_subscribing_twice_does_not_duplicate_anything(self):
        tracker = self.start()
        tracker.check(self.key)
        tracker.subscribe(self.key, "Anita", "console", "anita@example.com", "en")
        self.assertEqual(len(self.messages()), 1)
        self.assertEqual(len(self.store.subscribers_for(self.key)), 1)

    def test_unknown_project(self):
        tracker = self.tracker(date(2026, 11, 13))
        tracker.sync("gurugram")
        with self.assertRaises(KeyError):
            tracker.subscribe("gurugram:NOPE", "A", "console", "a@example.com")
        with self.assertRaises(KeyError):
            tracker.check("gurugram:NOPE")

    def test_inactive_subscribers_are_skipped(self):
        tracker = self.start()
        self.store.db.execute("UPDATE subscribers SET active = 0")
        self.store.db.commit()
        self.assertEqual(self.store.tracked_keys(), [])
        self.assertEqual(self.messages(), [])

    # -- delivery -------------------------------------------------------------
    def test_send_marks_messages_and_never_sends_twice(self):
        tracker = self.start()
        tracker.check(self.key)
        printed = []
        self.assertEqual(tracker.send(self.dir.name, out=printed.append), {"sent": 1, "failed": 0})
        self.assertTrue(any("Subject: Tracking started" in line for line in printed))
        self.assertEqual(tracker.send(self.dir.name, out=printed.append), {"sent": 0, "failed": 0})

    def test_failed_delivery_stays_queued_with_the_reason(self):
        tracker = self.start(channel="whatsapp", address="+910000000000")
        tracker.check(self.key)
        self.assertEqual(tracker.send(self.dir.name), {"sent": 0, "failed": 1})
        self.assertEqual(len(self.messages()), 1)
        error = self.store.db.execute("SELECT error FROM outbox").fetchone()["error"]
        self.assertIn("not set up yet", error)

    def test_file_channel_writes_one_file_per_message(self):
        tracker = self.start(channel="file", address="anita@example.com")
        tracker.check(self.key)
        outbox = os.path.join(self.dir.name, "outbox")
        self.assertEqual(tracker.send(outbox), {"sent": 1, "failed": 0})
        files = os.listdir(outbox)
        self.assertEqual(len(files), 1)
        with open(os.path.join(outbox, files[0]), encoding="utf-8") as handle:
            text = handle.read()
        self.assertTrue(text.startswith("To: anita@example.com\nSubject: Tracking started"))

    # -- reports and numbers --------------------------------------------------
    def test_status_report_reads_the_site_once_then_uses_the_store(self):
        tracker = self.start()
        text = tracker.status(self.key, "en")
        self.assertIn("Project ID: RERA-GRG-9001-2024", text)
        requests = len(self.site.calls)
        tracker.status(self.key, "hi")
        self.assertEqual(len(self.site.calls), requests)
        tracker.status(self.key, "en", refresh=True)
        self.assertGreater(len(self.site.calls), requests)

    def test_stats(self):
        self.site.set_list([
            listing(valid="2027-06-30"),
            fx.list_row(2, "RERA-GRG-1-2019", "A", "B", "30/06/2023", lapsed=True),
            fx.list_row(3, "RERA-GRG-2-2019", "C", "D", "30/06/2024", occ=True),
            fx.list_row(4, "RERA-GRG-3-2020", "E", "F", "15/01/2027"),
        ])
        tracker = self.tracker(date(2026, 11, 13))
        tracker.sync("gurugram")
        self.assertEqual(tracker.stats("gurugram"), {
            "projects": 4, "lapsed": 1, "with_occ": 1, "validity_passed": 2,
            "validity_passed_without_occ": 1, "validity_ends_within_180_days": 1, "with_quarterly_reports": 1,
        })

    def test_history_records_each_distinct_state_once(self):
        tracker = self.start()
        tracker.check(self.key)
        tracker.check(self.key)
        count = self.store.db.execute("SELECT COUNT(*) AS n FROM history").fetchone()["n"]
        self.assertEqual(count, 1)


class BuildStateTest(unittest.TestCase):
    LISTED = {"authority": "gurugram", "project_id": "RERA-GRG-9001-2024", "name": "S", "valid_upto": "2027-01-01",
              "lapsed": False, "occ": False}

    def test_parts_that_could_not_be_read_are_carried_over(self):
        previous = {"status": "OLD", "next_hearing": "x", "hearings": [{"date": "2025-01-01"}],
                    "quarters": [{"no": 1, "year": 2026}], "latest_report": {"quarter": [2026, 1]}}
        state = build_state(self.LISTED, True, None, None, None, previous)
        self.assertEqual(state["status"], "OLD")
        self.assertEqual(state["quarters"], [{"no": 1, "year": 2026}])
        self.assertEqual(state["latest_report"], {"quarter": [2026, 1]})

    def test_a_fresh_read_replaces_them(self):
        state = build_state(self.LISTED, True, {"status": "NEW", "next_hearing": None, "hearings": []}, [], None,
                            {"status": "OLD", "quarters": [{"no": 1, "year": 2026}]})
        self.assertEqual(state["status"], "NEW")
        self.assertEqual(state["quarters"], [])

    def test_no_previous_state_and_nothing_read(self):
        state = build_state(self.LISTED, False, None, None, None, None)
        self.assertNotIn("quarters", state)
        self.assertNotIn("status", state)
        self.assertFalse(state["listed"])
        self.assertEqual(state["list_url"], "https://haryanarera.gov.in/admincontrol/registered_projects/2")


if __name__ == "__main__":
    unittest.main()
