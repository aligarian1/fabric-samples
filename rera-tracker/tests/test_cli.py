import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from rera_tracker import cli
from rera_tracker.store import Store

from . import fixtures as fx
from .test_tracker import (DETAIL, HEARING, QUARTERS_TO_Q3, SCHEDULE, FakeSite, listing)


class CliTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.db = os.path.join(self.dir.name, "cli.db")
        self.outbox = os.path.join(self.dir.name, "outbox")
        self.site = FakeSite()
        self.site.set_list([listing(valid="2027-01-15"), fx.list_row(2, "RERA-GRG-1-2019", "OLD TOWERS", "SLOW HOMES", "30/06/2023", lapsed=True)])
        self.site.pages[DETAIL] = fx.detail_page("APPROVED AND CERTIFICATE UPLOADED", "NOT REQUIRED", [HEARING])
        self.site.pages[SCHEDULE] = fx.schedule_page(QUARTERS_TO_Q3)
        self.site.set_report(3, 2026, fx.report_page(submitted="15-Oct-2026"))
        patcher = mock.patch.object(cli, "PoliteFetcher", lambda **kwargs: self.site)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--db", self.db, "--today", "2026-11-13", "--delay", "0"] + list(args))
        return code, out.getvalue(), err.getvalue()

    def test_a_whole_working_day(self):
        code, out, _ = self.run_cli("sync", "gurugram")
        self.assertEqual((code, out.strip()), (0, "gurugram: 2 projects (2 new, 0 no longer listed)"))

        code, out, _ = self.run_cli("stats", "gurugram")
        self.assertEqual(code, 0)
        self.assertIn("projects                           2", out)
        self.assertIn("lapsed                             1", out)

        code, out, _ = self.run_cli("find", "sunrise")
        self.assertIn("RERA-GRG-9001-2024", out)
        self.assertNotIn("OLD TOWERS", out)

        code, out, _ = self.run_cli("subscribe", "rera-grg-9001-2024", "--name", "Anita", "--channel", "file",
                                    "--address", "anita@example.com", "--lang", "hi")
        self.assertEqual(code, 0)
        self.assertIn("Anita will get alerts for gurugram:RERA-GRG-9001-2024 by file.", out)

        code, out, _ = self.run_cli("check")
        self.assertIn("gurugram:RERA-GRG-9001-2024: baseline, registration_expiring (noted); 1 message(s) queued", out)

        code, out, _ = self.run_cli("send", "--outbox", self.outbox)
        self.assertEqual(out.strip(), "1 sent, 0 failed")
        files = os.listdir(self.outbox)
        self.assertEqual(len(files), 1)
        with open(os.path.join(self.outbox, files[0]), encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("ट्रैकिंग शुरू", text)

        code, out, _ = self.run_cli("report", "RERA-GRG-9001-2024")
        self.assertIn("Registration valid up to: 15 Jan 2027 (63 days left)", out)

        code, out, _ = self.run_cli("run", "--outbox", self.outbox)
        self.assertEqual(code, 0)
        self.assertIn("gurugram: 2 projects (0 new)", out)
        self.assertIn("panchkula: could not sync", out, "one list failing must not stop the rest of the run")
        self.assertIn("nothing new; 0 message(s) queued", out)
        self.assertIn("0 sent, 0 failed", out)
        store = Store(self.db)
        try:
            self.assertEqual(store.get_meta("last_run_problems"), "1")
            self.assertEqual(store.get_meta("last_run_checked"), "1")
            self.assertRegex(store.get_meta("last_run_at"), r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        finally:
            store.close()

    def test_the_daily_run_tidies_up_and_reports_problems_to_the_operator(self):
        self.run_cli("sync", "gurugram")
        store = Store(self.db)
        store.create_signup("old@example.com", "en", "gurugram:RERA-GRG-9001-2024", "v1", "2020-01-01T00:00:00Z")
        store.create_signup("new@example.com", "en", "gurugram:RERA-GRG-9001-2024", "v1", "2999-01-01T00:00:00Z")
        store.close()
        sent = []
        env = {"RERA_TRACKER_ADMIN_EMAIL": "boss@example.com"}
        with mock.patch.dict(os.environ, env), mock.patch.object(cli, "send_email", lambda *a: sent.append(a)):
            _code, out, _ = self.run_cli("run", "--outbox", self.outbox)
        self.assertIn("1 unconfirmed sign-up request(s) deleted", out)
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][0], "boss@example.com")
        self.assertIn("1 problem(s)", sent[0][1])
        self.assertIn("panchkula list", sent[0][2])
        store = Store(self.db)
        try:
            self.assertEqual(store.count_signups_since("old@example.com", "2000-01-01T00:00:00Z"), 0)
            self.assertEqual(store.count_signups_since("new@example.com", "2000-01-01T00:00:00Z"), 1)
        finally:
            store.close()

    def test_the_website_refuses_to_start_without_real_settings(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            code, _out, err = self.run_cli("serve")
        self.assertEqual(code, 2)
        self.assertIn("SECRET", err)
        self.assertIn("BUSINESS_NAME", err)

    def test_emails_from_the_command_line_get_stop_links_when_the_website_is_configured(self):
        env = {"RERA_TRACKER_BASE_URL": "https://tracker.example", "RERA_TRACKER_SECRET": "x" * 32}
        with mock.patch.dict(os.environ, env):
            self.run_cli("sync", "gurugram")
            self.run_cli("subscribe", "RERA-GRG-9001-2024", "--name", "A", "--channel", "file", "--address", "a@example.com")
            self.run_cli("check")
            self.run_cli("send", "--outbox", self.outbox)
        with open(os.path.join(self.outbox, os.listdir(self.outbox)[0]), encoding="utf-8") as handle:
            self.assertIn("https://tracker.example/unsubscribe?t=", handle.read())

    def test_clear_errors(self):
        with self.assertRaises(SystemExit) as nothing_yet:
            self.run_cli("report", "RERA-GRG-9001-2024")  # nothing synced yet
        self.assertIn("No stored project matches", str(nothing_yet.exception))
        self.run_cli("sync", "gurugram")
        with self.assertRaises(SystemExit) as unknown:
            self.run_cli("subscribe", "NO-SUCH-ID", "--name", "A", "--address", "a@example.com")
        self.assertIn("No stored project matches", str(unknown.exception))

    def test_a_broken_list_is_reported_not_stored(self):
        self.site.pages["https://haryanarera.gov.in/admincontrol/registered_projects/2"] = "<html>maintenance</html>"
        code, _out, err = self.run_cli("sync", "gurugram")
        self.assertEqual(code, 1)
        self.assertIn("error:", err)


if __name__ == "__main__":
    unittest.main()
