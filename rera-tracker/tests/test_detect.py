import unittest
from datetime import date

from rera_tracker.detect import (
    MAX_HEARING_EVENTS,
    diff_states,
    hearing_id,
    last_ended_quarter,
    latest_quarter,
    quarter_end,
    quarter_start,
)


def state(**changes):
    base = {
        "project_id": "RERA-GRG-9001-2024",
        "name": "SUNRISE HEIGHTS",
        "listed": True,
        "registered_on": "2024-02-01",
        "valid_upto": "2030-12-31",
        "lapsed": False,
        "occ": False,
        "corrigendum": False,
        "monitoring": False,
        "status": "APPROVED AND CERTIFICATE UPLOADED",
        "next_hearing": "NOT REQUIRED",
        "hearings": [{"date": "2025-04-21", "status": "APPROVED", "text": "Approved.", "order_url": None}],
        "quarters": [
            {"no": 2, "year": 2026, "start": "2026-04-01", "end": "2026-06-30"},
            {"no": 3, "year": 2026, "start": "2026-07-01", "end": "2026-09-30"},
        ],
        "latest_report": {"quarter": [2026, 3], "submitted_on": "2026-10-15", "values": {"collected_from_buyers": 1741.3}},
    }
    base.update(changes)
    return base


def kinds(events):
    return [e.kind for e in events]


TODAY = date(2026, 11, 12)


class QuarterMathTest(unittest.TestCase):
    def test_last_ended_quarter(self):
        self.assertEqual(last_ended_quarter(date(2026, 11, 12)), (3, 2026))
        self.assertEqual(last_ended_quarter(date(2026, 9, 30)), (2, 2026))
        self.assertEqual(last_ended_quarter(date(2026, 10, 1)), (3, 2026))
        self.assertEqual(last_ended_quarter(date(2027, 2, 20)), (4, 2026))
        self.assertEqual(last_ended_quarter(date(2027, 1, 1)), (4, 2026))

    def test_quarter_bounds(self):
        self.assertEqual(quarter_end(1, 2026), date(2026, 3, 31))
        self.assertEqual(quarter_end(4, 2026), date(2026, 12, 31))
        self.assertEqual(quarter_start(3, 2026), date(2026, 7, 1))

    def test_latest_quarter(self):
        self.assertEqual(latest_quarter(state())["no"], 3)
        self.assertIsNone(latest_quarter(state(quarters=[])))
        self.assertIsNone(latest_quarter(None))


class FirstRunTest(unittest.TestCase):
    def test_only_the_baseline_is_announced(self):
        events = diff_states(None, state(valid_upto="2026-06-30", lapsed=True), TODAY)
        self.assertEqual(kinds(events), ["baseline", "registration_expired"])
        self.assertFalse(events[0].silent)
        self.assertTrue(events[1].silent)

    def test_nothing_date_driven_when_all_is_in_order(self):
        self.assertEqual(kinds(diff_states(None, state(), TODAY)), ["baseline"])


class ChangeTest(unittest.TestCase):
    def test_no_change_no_events(self):
        self.assertEqual(diff_states(state(), state(), TODAY), [])

    def test_flags(self):
        events = diff_states(state(), state(lapsed=True, occ=True, corrigendum=True, monitoring=True), TODAY)
        self.assertEqual(kinds(events), ["marked_lapsed", "occ_uploaded", "corrigendum_added", "monitoring_started"])
        self.assertTrue(all(not e.silent for e in events))
        # A flag that was already set is not news.
        self.assertEqual(diff_states(state(lapsed=True), state(lapsed=True), TODAY), [])

    def test_validity_extended_or_changed(self):
        later = diff_states(state(valid_upto="2027-01-15"), state(valid_upto="2028-01-15"), date(2026, 6, 1))
        self.assertEqual(kinds(later), ["validity_extended"])
        self.assertEqual(later[0].data, {"old": "2027-01-15", "new": "2028-01-15"})
        self.assertEqual(later[0].key, "validity:2028-01-15")
        earlier = diff_states(state(valid_upto="2030-12-31"), state(valid_upto="2030-06-30"), TODAY)
        self.assertEqual(kinds(earlier), ["validity_changed"])

    def test_status_and_next_hearing(self):
        events = diff_states(state(), state(status="UNDER EXAMINATION", next_hearing="12-Jan-2027"), TODAY)
        self.assertEqual(kinds(events), ["status_changed", "next_hearing"])
        self.assertEqual(events[1].data, {"value": "12-Jan-2027"})
        # "NOT REQUIRED" is the site's way of saying there is no next date.
        self.assertEqual(diff_states(state(next_hearing="12-Jan-2027"), state(next_hearing="NOT REQUIRED"), TODAY), [])

    def test_new_hearings_newest_first_and_capped(self):
        many = [{"date": "2026-11-%02d" % d, "status": "ADJOURNMENT", "text": "Adjourned %d." % d, "order_url": None}
                for d in range(1, 9)]
        new = state(hearings=state()["hearings"] + many)
        events = diff_states(state(), new, TODAY)
        self.assertEqual(kinds(events), ["new_hearing"] * MAX_HEARING_EVENTS)
        self.assertEqual(events[0].data["date"], "2026-11-08")
        self.assertEqual(events[0].key, "hearing:" + hearing_id(many[-1]))

    def test_new_report_carries_the_previous_one(self):
        new = state(
            quarters=state()["quarters"] + [{"no": 4, "year": 2026, "start": "2026-10-01", "end": "2026-12-31"}],
            latest_report={"quarter": [2026, 4], "submitted_on": "2027-01-14", "values": {"collected_from_buyers": 900.0}},
        )
        events = diff_states(state(), new, date(2027, 1, 20))
        self.assertEqual(kinds(events), ["new_report"])
        self.assertEqual(events[0].key, "report:2026Q4")
        self.assertEqual(events[0].data["quarter"]["no"], 4)
        self.assertEqual(events[0].data["report"]["submitted_on"], "2027-01-14")
        self.assertEqual(events[0].data["previous"]["quarter"], [2026, 3])

    def test_removed_from_list(self):
        self.assertEqual(kinds(diff_states(state(), state(listed=False), TODAY)), ["removed_from_list"])


class FirstKnowledgeTest(unittest.TestCase):
    """A page that could not be read earlier must not turn old facts into news."""

    def test_quarters_first_read_on_a_later_run(self):
        old = state()
        del old["quarters"], old["latest_report"]
        self.assertEqual(diff_states(old, state(), TODAY), [])

    def test_project_page_first_read_on_a_later_run(self):
        old = state()
        for name in ("status", "next_hearing", "hearings"):
            del old[name]
        new = state(next_hearing="12-Jan-2027", hearings=state()["hearings"] * 1)
        self.assertEqual(diff_states(old, new, TODAY), [])


class DateDrivenTest(unittest.TestCase):
    def test_expiring_uses_the_tightest_threshold(self):
        ninety = diff_states(state(valid_upto="2027-01-15"), state(valid_upto="2027-01-15"), date(2026, 11, 12))
        self.assertEqual([(e.kind, e.key, e.data["days"]) for e in ninety],
                         [("registration_expiring", "expiring:90:2027-01-15", 64)])
        thirty = diff_states(state(valid_upto="2027-01-15"), state(valid_upto="2027-01-15"), date(2026, 12, 20))
        self.assertEqual([(e.key, e.data["days"]) for e in thirty], [("expiring:30:2027-01-15", 26)])
        far = diff_states(state(valid_upto="2027-01-15"), state(valid_upto="2027-01-15"), date(2026, 6, 1))
        self.assertEqual(far, [])

    def test_expired(self):
        events = diff_states(state(valid_upto="2026-06-30"), state(valid_upto="2026-06-30"), TODAY)
        self.assertEqual([(e.kind, e.key, e.data["days"]) for e in events],
                         [("registration_expired", "expired:2026-06-30", 135)])

    def test_expiry_is_not_reported_once_a_completion_certificate_is_on_record(self):
        done = state(valid_upto="2026-06-30", occ=True)
        self.assertEqual(diff_states(done, done, TODAY), [])

    def test_report_overdue_after_the_grace_period(self):
        quiet = state(quarters=[{"no": 2, "year": 2026, "start": "2026-04-01", "end": "2026-06-30"}])
        events = diff_states(quiet, quiet, TODAY)
        self.assertEqual([(e.kind, e.key) for e in events], [("report_overdue", "overdue:2026Q3")])
        self.assertEqual(events[0].data["quarter_end"], "2026-09-30")
        self.assertEqual(events[0].data["latest"]["no"], 2)
        # 20 days after the quarter ended is still inside the default 30-day grace period.
        self.assertEqual(diff_states(quiet, quiet, date(2026, 10, 20)), [])
        self.assertEqual(kinds(diff_states(quiet, quiet, date(2026, 10, 20), overdue_grace_days=10)), ["report_overdue"])

    def test_report_overdue_when_nothing_was_ever_filed(self):
        never = state(quarters=[], latest_report=None)
        self.assertEqual(kinds(diff_states(never, never, TODAY)), ["report_overdue"])
        # Registered during the quarter that just ended: its first report may not be due yet.
        fresh = state(quarters=[], latest_report=None, registered_on="2026-08-10")
        self.assertEqual(diff_states(fresh, fresh, TODAY), [])
        unknown = state(quarters=[], latest_report=None, registered_on=None)
        self.assertEqual(diff_states(unknown, unknown, TODAY), [])

    def test_overdue_needs_a_quarterly_list_and_no_completion_certificate(self):
        no_list = state()
        del no_list["quarters"]
        self.assertEqual(diff_states(no_list, no_list, date(2027, 6, 10)), [])
        done = state(occ=True)
        self.assertEqual(diff_states(done, done, date(2027, 6, 10)), [])
        self.assertEqual(kinds(diff_states(state(), state(), date(2027, 6, 10))), ["report_overdue"])


if __name__ == "__main__":
    unittest.main()
