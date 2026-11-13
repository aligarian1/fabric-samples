import unittest
from datetime import date

from rera_tracker.detect import Event
from rera_tracker.messages import fmt_date, fmt_money, quarter_label, render, render_status

TODAY = date(2026, 11, 12)

STATE = {
    "project_id": "RERA-GRG-9001-2024",
    "name": "SUNRISE HEIGHTS",
    "builder": "EXAMPLE BUILDERS PVT LTD",
    "location": "SECTOR 99 GURUGRAM",
    "district": "GURUGRAM",
    "reg_no": "GGM/900/1/2024/1 DATED 01.02.2024",
    "valid_upto": "2027-01-15",
    "lapsed": False,
    "occ": False,
    "status": "APPROVED AND CERTIFICATE UPLOADED",
    "next_hearing": "NOT REQUIRED",
    "detail_url": "https://haryanarera.gov.in/view_project/searchprojectDetail/9001",
    "hearings": [
        {"date": "2025-04-21", "status": "APPROVED", "text": "Approved subject to above.", "order_url": None},
        {"date": "2025-04-07", "status": "ADJOURNMENT", "text": "x" * 400, "order_url": None},
    ],
    "quarters": [{"no": 3, "year": 2026, "start": "2026-07-01", "end": "2026-09-30"}],
    "latest_report": {
        "quarter": [2026, 3],
        "submitted_on": "2026-10-15",
        "values": {
            "collected_from_buyers": 1741.3, "escrow_open": 35.08, "escrow_deposited": 1218.91,
            "escrow_withdrawn": 1047.43, "escrow_close": 206.56, "apartments_total": 240.0,
            "apartments_sold_in_quarter": 7.0,
        },
    },
}

EVENTS = [
    Event("baseline", "baseline"),
    Event("marked_lapsed", "lapsed"),
    Event("occ_uploaded", "occ"),
    Event("corrigendum_added", "corrigendum"),
    Event("monitoring_started", "monitoring"),
    Event("removed_from_list", "removed"),
    Event("validity_extended", "validity:2028-01-15", {"old": "2027-01-15", "new": "2028-01-15"}),
    Event("validity_changed", "validity:2026-12-31", {"old": "2027-01-15", "new": "2026-12-31"}),
    Event("registration_expired", "expired:2026-06-30", {"valid_upto": "2026-06-30", "days": 135}),
    Event("registration_expiring", "expiring:90:2027-01-15", {"valid_upto": "2027-01-15", "days": 64}),
    Event("status_changed", "status:X", {"old": "UNDER EXAMINATION", "new": "APPROVED"}),
    Event("next_hearing", "nexthearing:12-Jan-2027", {"value": "12-Jan-2027"}),
    Event("new_hearing", "hearing:abc", {"date": "2026-12-15", "status": "ADJOURNMENT",
                                          "text": "The matter is adjourned.", "order_url": "https://haryanarera.gov.in/o/1"}),
    Event("new_report", "report:2026Q4", {
        "quarter": {"no": 4, "year": 2026},
        "report": {"submitted_on": "2027-01-14", "values": {"collected_from_buyers": 900.0}},
        "previous": STATE["latest_report"],
    }),
    Event("report_overdue", "overdue:2026Q3", {"quarter_no": 3, "quarter_year": 2026, "quarter_end": "2026-09-30",
                                                "latest": {"no": 2, "year": 2026}}),
]


class FormattingTest(unittest.TestCase):
    def test_money_is_given_in_lakh_and_shown_in_lakh_or_crore(self):
        self.assertEqual(fmt_money(35.08, "en"), "₹35.08 lakh")
        self.assertEqual(fmt_money(1741.3, "en"), "₹17.41 crore")
        self.assertEqual(fmt_money(289445.6, "en"), "₹2,894.46 crore")
        self.assertEqual(fmt_money(-51.58, "en"), "₹-51.58 lakh")
        self.assertEqual(fmt_money(1741.3, "hi"), "₹17.41 करोड़")
        self.assertEqual(fmt_money(35.08, "hi"), "₹35.08 लाख")

    def test_dates_and_quarters(self):
        self.assertEqual(fmt_date("2026-10-15", "en"), "15 Oct 2026")
        self.assertEqual(fmt_date("2027-01-15", "hi"), "15 जनवरी 2027")
        self.assertEqual(fmt_date(None, "en"), "not shown")
        self.assertEqual(quarter_label(3, 2026, "en"), "Jul–Sep 2026")
        self.assertEqual(quarter_label(4, 2026, "hi"), "अक्टूबर–दिसंबर 2026")

    def test_unknown_language_falls_back_to_english(self):
        self.assertEqual(fmt_date("2026-10-15", "fr"), "15 Oct 2026")


class StatusReportTest(unittest.TestCase):
    def test_english(self):
        text = render_status(STATE, TODAY, "en")
        for expected in (
            "SUNRISE HEIGHTS (EXAMPLE BUILDERS PVT LTD)",
            "Project ID: RERA-GRG-9001-2024",
            "Location: SECTOR 99 GURUGRAM, GURUGRAM",
            "Registration valid up to: 15 Jan 2027 (64 days left)",
            "Listed as a lapsed project: No",
            "OC/CC/PCC on record: No",
            "Quarterly reports on record: 1",
            "Latest report: Jul–Sep 2026, filed on 15 Oct 2026",
            "  Collected from buyers in the quarter: ₹17.41 crore",
            "  Project bank account: opened at ₹35.08 lakh, ₹12.19 crore deposited, ₹10.47 crore withdrawn, closed at ₹2.07 crore",
            "  Units sold in the quarter: 7 (the project has 240)",
            "  21 Apr 2025 — APPROVED: Approved subject to above.",
            "Official page: https://haryanarera.gov.in/view_project/searchprojectDetail/9001",
            "This is information, not legal advice.",
        ):
            self.assertIn(expected, text)
        self.assertNotIn("x" * 300, text)  # long hearing notes are shortened
        self.assertNotIn("! ", text)

    def test_hindi(self):
        text = render_status(STATE, TODAY, "hi")
        for expected in (
            "रजिस्ट्रेशन की वैधता: 15 जनवरी 2027 (64 दिन बाकी)",
            "लैप्स्ड प्रोजेक्ट के रूप में दर्ज: नहीं",
            "सबसे ताज़ा रिपोर्ट: जुलाई–सितंबर 2026, 15 अक्टूबर 2026 को दाखिल",
            "इस तिमाही में खरीदारों से मिली रकम: ₹17.41 करोड़",
            "यह केवल जानकारी है, कानूनी सलाह नहीं।",
        ):
            self.assertIn(expected, text)

    def test_passed_validity_and_missing_report_are_flagged(self):
        late = dict(STATE, valid_upto="2026-06-30", lapsed=True,
                    quarters=[{"no": 2, "year": 2026, "start": "2026-04-01", "end": "2026-06-30"}])
        text = render_status(late, TODAY, "en")
        self.assertIn("Registration valid up to: 30 Jun 2026 (passed 135 days ago)", text)
        self.assertIn("Listed as a lapsed project: Yes", text)
        self.assertIn("! No quarterly report for the quarter that ended on 30 Sep 2026 appears on the HRERA site as of 12 Nov 2026.", text)

    def test_minimal_state_does_not_crash(self):
        text = render_status({"project_id": "REG-119-OF-2017", "name": "LEGACY COURT", "valid_upto": None}, TODAY, "en")
        self.assertIn("Registration valid up to: not shown", text)
        self.assertIn("Official page: https://haryanarera.gov.in", text)


class EventMessagesTest(unittest.TestCase):
    def test_every_event_renders_in_both_languages(self):
        for event in EVENTS:
            for lang in ("en", "hi"):
                subject, body = render(event, STATE, TODAY, lang)
                self.assertIn("SUNRISE HEIGHTS", subject, event.kind)
                self.assertIn("haryanarera.gov.in", body, event.kind)
                self.assertNotIn("{", body, event.kind)
                self.assertGreater(len(body.splitlines()), 3, event.kind)

    def test_new_report_compares_with_the_previous_one(self):
        subject, body = render(EVENTS[-2], STATE, TODAY, "en")
        self.assertEqual(subject, "New quarterly report filed — SUNRISE HEIGHTS (EXAMPLE BUILDERS PVT LTD)")
        self.assertIn("The builder filed the report for Oct–Dec 2026 on 14 Jan 2027.", body)
        self.assertIn("Collected from buyers in the quarter: ₹9.00 crore (previous report: ₹17.41 crore)", body)

    def test_overdue_names_the_latest_report(self):
        _subject, body = render(EVENTS[-1], STATE, TODAY, "en")
        self.assertIn("No quarterly report for the quarter that ended on 30 Sep 2026 appears on the HRERA site as of 12 Nov 2026.", body)
        self.assertIn("The latest report on record is for Apr–Jun 2026.", body)
        _subject, hindi = render(EVENTS[-1], STATE, TODAY, "hi")
        self.assertIn("30 सितंबर 2026 को समाप्त तिमाही की रिपोर्ट 12 नवंबर 2026 तक HRERA की साइट पर नहीं दिखी।", hindi)

    def test_dates_in_messages(self):
        _subject, expired = render(EVENTS[8], STATE, TODAY, "en")
        self.assertIn("The registration was valid up to 30 Jun 2026, which was 135 days ago.", expired)
        _subject, extended = render(EVENTS[6], STATE, TODAY, "en")
        self.assertIn("The registration was valid up to 15 Jan 2027. The HRERA list now shows 15 Jan 2028.", extended)
        _subject, hearing = render(EVENTS[12], STATE, TODAY, "en")
        self.assertIn("Hearing on 15 Dec 2026. Status: ADJOURNMENT.", hearing)
        self.assertIn("Order: https://haryanarera.gov.in/o/1", hearing)


if __name__ == "__main__":
    unittest.main()
