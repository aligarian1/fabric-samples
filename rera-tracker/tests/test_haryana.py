import unittest
from datetime import date

from rera_tracker import haryana
from rera_tracker.fetch import FetchError
from rera_tracker.tables import parse_tables, plain_text, to_number

from . import fixtures as fx


class TablesTest(unittest.TestCase):
    def test_cells_keep_text_links_popups_and_forms(self):
        html = (
            "<table><thead><tr><th>A</th><th>B</th><th>C</th></tr></thead><tbody><tr>"
            '<td> one<br>two </td><td><a href="https://x.example/p">link</a>'
            "<a onclick=\"window.open('https://x.example/pop','w','height=5');\">View</a></td>"
            '<td><form action="https://x.example/f" method="post"><input type="hidden" name="q" value="3">'
            '<input type="submit" name="submit" value="View"></form></td></tr></tbody></table>'
        )
        table = parse_tables(html).tables[0]
        self.assertEqual(table.headers, ["A", "B", "C"])
        row = table.rows[0]
        self.assertEqual(row[0].text, "one two")
        self.assertEqual(row[1].links, ["https://x.example/p"])
        self.assertEqual(row[1].popups, ["https://x.example/pop"])
        self.assertEqual(row[2].forms[0].action, "https://x.example/f")
        self.assertEqual(row[2].forms[0].fields, {"q": "3", "submit": "View"})

    def test_scripts_comments_and_stray_tags_are_ignored(self):
        html = fx._PAGE_TOP + "<table><tr><td>kept</td><!-- <td>dropped</td> --></tr></table>"
        tables = parse_tables(html).tables
        self.assertEqual([c.text for c in tables[-1].rows[0]], ["kept"])
        self.assertNotIn("noBack", plain_text(html))

    def test_one_cell_table_titles_the_next_table(self):
        html = "<table><tr><td><b>Cash Inflow</b></td></tr></table><table><tr><td>Total</td><td>5</td></tr></table>"
        tables = parse_tables(html).tables
        self.assertEqual(tables[1].heading, "Cash Inflow")

    def test_unclosed_table_is_still_returned(self):
        tables = parse_tables("<table><tr><td>a</td><td>b").tables
        self.assertEqual([c.text for c in tables[0].rows[0]], ["a", "b"])

    def test_to_number(self):
        self.assertEqual(to_number("1,234.50"), 1234.5)
        self.assertEqual(to_number("-51.58"), -51.58)
        self.assertEqual(to_number(" 0 "), 0.0)
        self.assertIsNone(to_number("3 of 2025"))
        self.assertIsNone(to_number("28-11-2024"))
        self.assertIsNone(to_number(""))


class DatesTest(unittest.TestCase):
    def test_formats_used_on_the_site(self):
        self.assertEqual(haryana.parse_date("27/11/2029"), date(2029, 11, 27))
        self.assertEqual(haryana.parse_date("21-Sep-2021"), date(2021, 9, 21))
        self.assertEqual(haryana.parse_date("15-10-2026"), date(2026, 10, 15))
        self.assertEqual(haryana.parse_date("01.05.2025"), date(2025, 5, 1))
        self.assertEqual(haryana.parse_date("2025-04-02"), date(2025, 4, 2))

    def test_placeholders_and_rubbish_give_none(self):
        for text in ("", "--", "01/01/1970", "31/02/2026", "NOT REQUIRED", "32-Foo-2026"):
            self.assertIsNone(haryana.parse_date(text), text)


class RegisteredProjectsTest(unittest.TestCase):
    def setUp(self):
        self.html = fx.list_page([
            fx.list_row(1, "RERA-GRG-9001-2024", "SUNRISE HEIGHTS", "EXAMPLE BUILDERS PVT LTD", "15/01/2027",
                        reg_no="GGM/900/1/2024/1 DATED 01.02.2024", site_id=9001, qpr_token="OTAwMQ=="),
            fx.list_row(2, "RERA-GRG-9002-2021", "OLD TOWERS", "SLOW HOMES LTD", "31/03/2025",
                        reg_no="GGM/486/218/2021/54 DATED 21.09.2021", site_id=9002, qpr_token="OTAwMg==",
                        lapsed=True, corrigendum=True, monitoring=True),
            fx.list_row(3, "RERA-GRG-9003-2019", "DONE RESIDENCY", "QUICK BUILD LLP", "30/06/2023", site_id=9003, occ=True),
            fx.list_row(4, "NA", "LEGACY PLAZA", "LEGACY DEVELOPERS", "01/01/1970", reg_no="384 OF 2017 (SUPERSEDED BY 06 OF 2018)"),
            fx.list_row(5, "NA", "LEGACY COURT", "LEGACY DEVELOPERS", "30/06/2018", reg_no="119 OF 2017 DATED 28.08.2017"),
            fx.list_row(6, "RERA-GRG-9001-2024", "SUNRISE HEIGHTS (DUPLICATE ROW)", "EXAMPLE BUILDERS PVT LTD", "15/01/2027", site_id=9001),
        ])
        self.projects = haryana.parse_registered_projects(self.html, "gurugram")
        self.by_id = {p.project_id: p for p in self.projects}

    def test_rows_are_read_and_duplicates_dropped(self):
        self.assertEqual(len(self.projects), 5)
        self.assertEqual(self.by_id["RERA-GRG-9001-2024"].name, "SUNRISE HEIGHTS")

    def test_ordinary_project(self):
        p = self.by_id["RERA-GRG-9001-2024"]
        self.assertEqual(p.key, "gurugram:RERA-GRG-9001-2024")
        self.assertEqual(p.builder, "EXAMPLE BUILDERS PVT LTD")
        self.assertEqual(p.location, "SECTOR 99 GURUGRAM")
        self.assertEqual(p.valid_upto, "2027-01-15")
        self.assertEqual(p.registered_on, "2024-02-01")
        self.assertEqual(p.site_id, 9001)
        self.assertEqual(p.detail_url, fx.detail_url(9001))
        self.assertEqual(p.qpr_url, fx.qpr_url("OTAwMQ=="))
        self.assertTrue(p.form_url.endswith("/view_project/project_preview_open/9001"))
        self.assertTrue(p.certificate_url.endswith("/view_project/view_certificate/TOKEN1"))
        self.assertFalse(p.lapsed or p.corrigendum or p.occ or p.monitoring)

    def test_flags(self):
        old = self.by_id["RERA-GRG-9002-2021"]
        self.assertTrue(old.lapsed and old.corrigendum and old.monitoring)
        self.assertEqual(old.reg_no, "GGM/486/218/2021/54 DATED 21.09.2021")
        self.assertTrue(old.monitoring_url.endswith("/view_monitoring_cases/MON2"))
        self.assertTrue(self.by_id["RERA-GRG-9003-2019"].occ)
        self.assertIsNone(self.by_id["RERA-GRG-9003-2019"].qpr_url)

    def test_projects_without_an_id_get_one_from_the_registration_number(self):
        legacy = self.by_id["REG-384-OF-2017"]
        self.assertEqual(legacy.name, "LEGACY PLAZA")
        self.assertIsNone(legacy.valid_upto)
        self.assertIsNone(legacy.detail_url)
        self.assertEqual(self.by_id["REG-119-OF-2017"].registered_on, "2017-08-28")

    def test_missing_table_is_an_error(self):
        with self.assertRaises(haryana.ParseError):
            haryana.parse_registered_projects("<html><body>Site under maintenance</body></html>", "gurugram")
        with self.assertRaises(ValueError):
            haryana.parse_registered_projects(self.html, "mumbai")


class QuarterlyTest(unittest.TestCase):
    def test_schedule(self):
        html = fx.schedule_page([
            (3, 2026, "01-Jul-2026", "30-Sep-2026"),
            (1, 2026, "01-Jan-2026", "31-Mar-2026"),
            (2, 2026, "01-Apr-2026", "30-Jun-2026"),
        ])
        quarters = haryana.parse_quarter_schedule(html)
        self.assertEqual([(q.year, q.no) for q in quarters], [(2026, 1), (2026, 2), (2026, 3)])
        latest = quarters[-1]
        self.assertEqual((latest.start, latest.end), ("2026-07-01", "2026-09-30"))
        self.assertTrue(latest.action.endswith("/view_project/quaterly_schedule_preview_open"))
        self.assertEqual(latest.fields, {
            "quarter_no": "3", "quarter_year": "2026", "reracode_project": "2",
            "temp_project_id": "9001", "temp_project_year": "2024", "submit": "View",
        })
        self.assertEqual(latest.to_dict(), {"no": 3, "year": 2026, "start": "2026-07-01", "end": "2026-09-30"})

    def test_empty_schedule_and_missing_table(self):
        self.assertEqual(haryana.parse_quarter_schedule(fx.schedule_page([])), [])
        with self.assertRaises(haryana.ParseError):
            haryana.parse_quarter_schedule("<html><body>nothing</body></html>")

    def test_report(self):
        report = haryana.parse_quarter_report(fx.report_page())
        self.assertEqual(report.submitted_on, "2026-10-15")
        self.assertEqual(report.values, {
            "collected_from_buyers": 1741.3,
            "loans_availed": 0.0,
            "inflow_total": 33961.56,
            "outflow_total": 656.76,
            "escrow_open": 35.08,
            "escrow_deposited": 1218.91,
            "escrow_withdrawn": 1047.43,
            "escrow_close": 206.56,
            "apartments_total": 240.0,
            "estimated_cost": 6980.07,
            "apartments_sold_in_quarter": 7.0,
        })
        self.assertEqual(len(report.documents), 2)
        self.assertEqual(report.documents[0]["uploaded_on"], "2026-10-15")

    def test_report_without_content_is_an_error(self):
        with self.assertRaises(haryana.ParseError):
            haryana.parse_quarter_report("<html><body>No record found</body></html>")


class DetailTest(unittest.TestCase):
    def test_detail(self):
        long_text = "word " * 400
        html = fx.detail_page("APPROVED AND CERTIFICATE UPLOADED", "NOT REQUIRED", [
            {"date": "21-Apr-2025", "text": "Approved subject to above.", "status": "APPROVED", "order": "NjE2Mw=="},
            {"date": "07-Apr-2025", "text": long_text, "status": "ADJOURNMENT"},
        ])
        detail = haryana.parse_project_detail(html)
        self.assertEqual(detail.status, "APPROVED AND CERTIFICATE UPLOADED")
        self.assertEqual(detail.next_hearing, "NOT REQUIRED")
        self.assertEqual(len(detail.hearings), 2)
        first, second = detail.hearings
        self.assertEqual((first.date, first.status, first.text), ("2025-04-21", "APPROVED", "Approved subject to above."))
        self.assertTrue(first.order_url.endswith("/view_project/viewOrderPdf/NjE2Mw=="))
        self.assertIsNone(second.order_url)
        self.assertLessEqual(len(second.text), 601)
        self.assertTrue(second.text.endswith("…"))

    def test_missing_tables_are_an_error(self):
        with self.assertRaises(haryana.ParseError):
            haryana.parse_project_detail("<html><body>Session expired</body></html>")


class SourceSafetyTest(unittest.TestCase):
    class Recorder:
        def __init__(self):
            self.calls = []

        def get(self, url):
            self.calls.append(url)
            raise FetchError("should not be reached in this test")

        post = get

    def test_urls_outside_the_site_are_never_fetched(self):
        recorder = self.Recorder()
        source = haryana.HaryanaSource(recorder)
        for bad in ("https://evil.example/view_project/searchprojectDetail/1",
                    "http://haryanarera.gov.in/view_project/searchprojectDetail/1",
                    "https://haryanarera.gov.in.evil.example/x"):
            with self.assertRaises(ValueError):
                source.fetch_detail(bad)
            with self.assertRaises(ValueError):
                source.fetch_quarters(bad)
            with self.assertRaises(ValueError):
                source.fetch_report(haryana.Quarter(1, 2026, action=bad))
        self.assertEqual(recorder.calls, [])

    def test_list_urls(self):
        self.assertEqual(haryana.HaryanaSource.list_url("gurugram"), "https://haryanarera.gov.in/admincontrol/registered_projects/2")
        self.assertEqual(haryana.HaryanaSource.list_url("panchkula"), "https://haryanarera.gov.in/admincontrol/registered_projects/1")


if __name__ == "__main__":
    unittest.main()
