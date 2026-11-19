import html
import io
import json
import os
import re
import tempfile
import unittest
from datetime import date, datetime, timezone
from unittest import mock
from urllib.parse import parse_qs, urlencode, urlsplit
from wsgiref.util import setup_testing_defaults

from rera_tracker import tokens, web
from rera_tracker.haryana import HaryanaSource
from rera_tracker.notify import DeliveryError
from rera_tracker.store import Store
from rera_tracker.tracker import Tracker

from . import fixtures as fx
from .test_tracker import DETAIL, HEARING, QUARTERS_TO_Q3, SCHEDULE, Clock, FakeSite, listing

START = datetime(2026, 11, 19, 10, 0, tzinfo=timezone.utc).timestamp()
SECRET = "a-long-random-test-secret-0123456789"
BASE = "https://tracker.example"
KEY = "gurugram:RERA-GRG-9001-2024"
PAGE = "/p/gurugram/RERA-GRG-9001-2024"


class FakeClock:
    def __init__(self, start=START):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class Resp:
    def __init__(self, status, headers, body):
        self.code = int(status.split()[0])
        self.headers = {k.lower(): v for k, v in headers}
        self.text = body.decode("utf-8")


class Client:
    def __init__(self, app, ip="203.0.113.7"):
        self.app, self.ip = app, ip

    def request(self, method, url, data=None, raw=None, content_type="application/x-www-form-urlencoded", extra=None):
        parts = urlsplit(url)
        environ = {}
        setup_testing_defaults(environ)
        environ.update({"REQUEST_METHOD": method, "PATH_INFO": parts.path, "QUERY_STRING": parts.query,
                        "REMOTE_ADDR": self.ip})
        body = raw if raw is not None else (urlencode(data).encode("utf-8") if data is not None else b"")
        if method == "POST":
            environ.update({"CONTENT_TYPE": content_type, "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body)})
        environ.update(extra or {})
        captured = {}

        def start_response(status, headers):
            captured["status"], captured["headers"] = status, headers

        chunks = self.app(environ, start_response)
        return Resp(captured["status"], captured["headers"], b"".join(chunks))

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, data=None, **kwargs):
        return self.request("POST", url, data=data, **kwargs)


def local(url):
    """Path and query of an absolute link, as the browser would request it."""
    parts = urlsplit(html.unescape(url))
    return parts.path + ("?" + parts.query if parts.query else "")


class WebCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.db = os.path.join(self.dir.name, "web.db")
        self.clock = FakeClock()
        self.mail = []
        self.mail_error = None
        self.cfg = web.WebConfig(
            db_path=self.db, secret=SECRET, base_url=BASE, business_name="Example & Co", contact_email="help@example.com",
            sender=self.send_mail, clock=self.clock,
        )
        # A small copy of the Haryana site, read by the real tracker code.
        site = FakeSite()
        site.set_list([listing(valid="2027-06-30"),
                       fx.list_row(2, "RERA-GRG-1-2019", "OLD TOWERS", "SLOW HOMES LTD", "30/06/2023", lapsed=True)])
        site.pages[DETAIL] = fx.detail_page("APPROVED AND CERTIFICATE UPLOADED", "NOT REQUIRED", [HEARING])
        site.pages[SCHEDULE] = fx.schedule_page(QUARTERS_TO_Q3)
        site.set_report(3, 2026, fx.report_page(submitted="15-Oct-2026"))
        self.site = site
        store = Store(self.db)
        self.addCleanup(store.close)
        self.store = store
        self.tracker = Tracker(store, HaryanaSource(site), today=date(2026, 11, 19), now=Clock())
        self.tracker.sync("gurugram")
        self.app = web.create_app(self.cfg)
        self.client = Client(self.app)

    def send_mail(self, to, subject, body, headers):
        if self.mail_error:
            raise self.mail_error
        self.mail.append({"to": to, "subject": subject, "body": body, "headers": headers})

    # -- helpers -------------------------------------------------------------
    def track(self):
        """Make the first project a followed one, so its page shows the full record."""
        self.tracker.subscribe(KEY, "Op", "console", "op@example.com", "en")
        self.tracker.check(KEY)

    def form_token(self, path=PAGE):
        return re.search(r'name="ft" value="([^"]+)"', self.client.get(path).text).group(1)

    def signup(self, token=None, wait=5, query="", **fields):
        if token is None:
            token = self.form_token()
        self.clock.advance(wait)
        data = {"authority": "gurugram", "project_id": "RERA-GRG-9001-2024", "ft": token, "email": "anita@example.com",
                "email_lang": "en", "consent": "yes", "website": ""}
        data.update(fields)
        return self.client.post("/subscribe" + query, data=data)

    def confirm_link(self, mail=None):
        mail = mail or self.mail[-1]
        return local(re.search(r"https://tracker\.example/confirm\?\S+", mail["body"]).group(0))

    def confirm(self, link=None):
        link = link or self.confirm_link()
        token = parse_qs(urlsplit(link).query)["t"][0]
        return self.client.post(link, data={"t": token})

    def subscribe_fully(self, email="anita@example.com", lang="en", project_id="RERA-GRG-9001-2024"):
        self.signup(email=email, email_lang=lang, project_id=project_id)
        return self.confirm()

    def unsub_link(self, subscriber_id, lang="en", key=None):
        return local(self.app.unsubscribe_url(subscriber_id, lang, key))


class PagesTest(WebCase):
    def test_every_response_carries_security_headers(self):
        for path in ("/", "/privacy", "/search?q=sun", PAGE, "/nope", "/robots.txt", "/sitemap.xml", "/health"):
            response = self.client.get(path)
            h = response.headers
            self.assertIn("default-src 'none'", h["content-security-policy"], path)
            self.assertNotIn("script-src", h["content-security-policy"], path)
            self.assertEqual(h["x-content-type-options"], "nosniff", path)
            self.assertEqual(h["x-frame-options"], "DENY", path)
            self.assertEqual(h["referrer-policy"], "no-referrer", path)
            self.assertIn("max-age=", h["strict-transport-security"], path)

    def test_home_in_english_and_hindi(self):
        english = self.client.get("/")
        self.assertEqual(english.code, 200)
        self.assertIn('<html lang="en">', english.text)
        self.assertIn("Follow your flat&#x27;s RERA record", english.text)
        self.assertIn("Covers 2 projects", english.text)
        self.assertIn('href="/?lang=hi"', english.text)
        hindi = self.client.get("/?lang=hi")
        self.assertIn('<html lang="hi">', hindi.text)
        self.assertIn("अपने फ़्लैट का RERA रिकॉर्ड फ़ॉलो करें", hindi.text)
        self.assertIn('href="/"', hindi.text)
        self.assertIn("स्वतंत्र सेवा", hindi.text)
        self.assertEqual(self.client.get("/?lang=xx").text, english.text)
        # The switch link names the OTHER language, in that language's own script.
        self.assertIn('<a href="/?lang=hi" lang="hi">हिन्दी</a>', english.text)
        self.assertIn('<a href="/" lang="en">English</a>', hindi.text)
        self.assertNotIn(">Home</a>", english.text)

    def test_search(self):
        found = self.client.get("/search?q=sunrise")
        self.assertIn('href="/p/gurugram/RERA-GRG-9001-2024"', found.text)
        self.assertNotIn("OLD TOWERS", found.text)
        old = self.client.get("/search?q=old")
        self.assertIn("listed as lapsed", old.text)
        self.assertIn("valid to 30 Jun 2023", old.text)
        self.assertIn("No project matched", self.client.get("/search?q=zzzz").text)
        self.assertIn("at least 2 characters", self.client.get("/search?q=a").text)
        self.assertIn('href="/p/gurugram/RERA-GRG-1-2019?lang=hi"', self.client.get("/search?q=old&lang=hi").text)

    def test_nothing_from_the_database_or_the_url_reaches_the_page_unescaped(self):
        self.store.upsert_listed("gurugram", [{
            "key": "gurugram:X-1", "authority": "gurugram", "project_id": "X-1",
            "name": "<script>alert(1)</script>", "builder": "\"><img src=x onerror=alert(2)>",
            "location": "<b>bold</b>", "district": "D", "valid_upto": "2027-01-01", "lapsed": False, "occ": False,
        }], "2026-11-19T00:00:00Z")
        for url in ("/search?q=%3Cscript%3E", "/p/gurugram/X-1", "/search?q=%22%3E%3Cimg+src%3Dx%3E", "/privacy"):
            text = self.client.get(url).text
            for danger in ("<script>alert", "<img src=x", "<b>bold</b>", "onerror=alert(2)>"):
                self.assertNotIn(danger, text, (url, danger))
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", self.client.get("/p/gurugram/X-1").text)
        self.assertIn("&quot;&gt;&lt;img src=x onerror=alert(2)&gt;", self.client.get("/p/gurugram/X-1").text)
        self.assertNotIn("<script", self.client.get("/p/gurugram/X-1").text.lower(), "the site has no scripts at all")

    def test_project_page_before_anyone_follows_it(self):
        page = self.client.get("/p/gurugram/RERA-GRG-1-2019")
        self.assertEqual(page.code, 200)
        self.assertIn("OLD TOWERS", page.text)
        self.assertIn("SLOW HOMES LTD", page.text)
        self.assertIn("Listed as a lapsed project", page.text)
        self.assertIn("Project list read on 13 Nov 2026", page.text)
        self.assertIn("added once someone follows this project", page.text)
        self.assertIn('rel="canonical" href="https://tracker.example/p/gurugram/RERA-GRG-1-2019"', page.text)
        self.assertIn('hreflang="hi" href="https://tracker.example/p/gurugram/RERA-GRG-1-2019?lang=hi"', page.text)

    def test_project_page_for_a_followed_project_shows_the_full_record(self):
        self.track()
        page = self.client.get(PAGE)
        for expected in ("SUNRISE HEIGHTS", "EXAMPLE BUILDERS PVT LTD", "Quarterly reports on record: 2",
                         "Collected from buyers in the quarter", "Official record read on",
                         "APPROVED AND CERTIFICATE UPLOADED", "Recent hearing entries"):
            self.assertIn(expected, page.text)
        hindi = self.client.get(PAGE + "?lang=hi")
        self.assertIn("दर्ज तिमाही रिपोर्ट: 2", hindi.text)
        self.assertIn("हाल की सुनवाई", hindi.text)

    def test_unknown_things_are_404(self):
        for url in ("/p/gurugram/NO-SUCH", "/p/delhi/RERA-GRG-9001-2024", "/p/gurugram/a%20b", "/p/gurugram/", "/nothing",
                    "/privacy/", "/p/gurugram/RERA-GRG-9001-2024/extra"):
            self.assertEqual(self.client.get(url).code, 404, url)

    def test_head_gets_headers_but_no_body(self):
        response = self.client.request("HEAD", PAGE)
        self.assertEqual((response.code, response.text), (200, ""))
        self.assertGreater(int(response.headers["content-length"]), 500)

    def test_wrong_methods(self):
        self.assertEqual(self.client.post("/").code, 405)
        self.assertEqual(self.client.post(PAGE).code, 405)
        response = self.client.get("/subscribe")
        self.assertEqual((response.code, response.headers["allow"]), (405, "POST"))
        self.assertEqual(self.client.request("DELETE", "/").code, 405)

    def test_privacy_notice_names_the_business_and_the_contact(self):
        page = self.client.get("/privacy").text
        self.assertIn("Example &amp; Co runs this website. Contact: help@example.com.", page)
        self.assertIn("If you do not confirm within 7 days, we delete the request.", page)
        self.assertIn("2026-11-v1", page)
        self.assertIn("गोपनीयता सूचना", self.client.get("/privacy?lang=hi").text)

    def test_sitemap_and_robots(self):
        sitemap = self.client.get("/sitemap.xml")
        self.assertIn("application/xml", sitemap.headers["content-type"])
        self.assertIn("<loc>https://tracker.example/p/gurugram/RERA-GRG-9001-2024</loc>", sitemap.text)
        self.assertIn("<loc>https://tracker.example/</loc>", sitemap.text)
        robots = self.client.get("/robots.txt").text
        self.assertIn("Sitemap: https://tracker.example/sitemap.xml", robots)
        self.assertIn("Disallow: /unsubscribe", robots)

    def test_health_goes_red_when_the_daily_job_stops(self):
        fresh = json.loads(self.client.get("/health").text)
        self.assertEqual((fresh["ok"], fresh["projects"], fresh["last_run"]), (True, 2, None))
        self.store.set_meta("last_run_at", "2026-11-19T06:00:00Z")
        self.store.set_meta("last_run_problems", "3")
        report = self.client.get("/health")
        self.assertEqual((report.code, json.loads(report.text)["last_run_problems"]), (200, 3))
        self.clock.advance(40 * 3600)
        late = self.client.get("/health")
        self.assertEqual(late.code, 503)
        self.assertTrue(json.loads(late.text)["stale"])

    def test_a_bug_shows_a_calm_page_and_is_logged(self):
        errors = io.StringIO()
        with mock.patch.object(web.App, "home", side_effect=RuntimeError("boom")):
            response = self.client.get("/", extra={"wsgi.errors": errors})
        self.assertEqual(response.code, 500)
        self.assertIn("Something went wrong", response.text)
        self.assertNotIn("boom", response.text)
        self.assertIn("RuntimeError: boom", errors.getvalue())

    def test_incomplete_settings_stop_the_site_from_starting(self):
        with self.assertRaises(web.ConfigError) as caught:
            web.create_app(web.WebConfig(db_path=self.db, secret="short", base_url="http://example.com"))
        message = str(caught.exception)
        for needed in ("SECRET", "BASE_URL", "BUSINESS_NAME", "CONTACT_EMAIL"):
            self.assertIn(needed, message)
        web.create_app(web.dev_config(web.WebConfig(db_path=self.db), 8080))


class SignupTest(WebCase):
    def test_the_whole_journey(self):
        page = self.client.get(PAGE).text
        self.assertIn('action="/subscribe"', page)
        self.assertIn("I agree that Example &amp; Co may use my email address", page)
        sent = self.signup(email="Anita.Kumar@Example.COM")
        self.assertEqual(sent.code, 200)
        self.assertIn("Check your email", sent.text)
        self.assertEqual(len(self.mail), 1)
        mail = self.mail[0]
        self.assertEqual(mail["to"], "anita.kumar@example.com")
        self.assertEqual(mail["subject"], "Confirm your alerts for SUNRISE HEIGHTS")
        self.assertIn("EXAMPLE BUILDERS PVT LTD", mail["body"])
        self.assertIn("works for 7 days", mail["body"])
        # Nothing is active yet.
        self.assertFalse(self.store.is_subscribed("email", "anita.kumar@example.com", KEY))
        link = self.confirm_link()
        visit = self.client.get(link)
        self.assertEqual(visit.code, 200)
        self.assertIn("Yes, send me alerts", visit.text)
        self.assertFalse(self.store.is_subscribed("email", "anita.kumar@example.com", KEY), "a visit alone must not confirm")
        done = self.confirm(link)
        self.assertIn("Alerts are on", done.text)
        self.assertTrue(self.store.is_subscribed("email", "anita.kumar@example.com", KEY))
        signup = self.store.get_signup(1)
        self.assertEqual((signup["notice_version"], signup["lang"]), ("2026-11-v1", "en"))
        self.assertTrue(signup["confirmed_at"] and signup["subscriber_id"])
        self.assertIn("Alerts are on", self.confirm(link).text, "confirming twice is harmless")
        self.assertEqual(len(self.store.subscribers_for(KEY)), 1)

    def test_first_report_and_every_later_alert_carry_a_personal_stop_link(self):
        self.track()
        self.signup()
        self.confirm()
        subscriber = self.store.get_subscriber("email", "anita@example.com")
        queued = [m for m in self.store.pending_messages() if m["address"] == "anita@example.com"]
        self.assertEqual(len(queued), 1)
        self.assertIn("Stop these alerts or delete your data: https://tracker.example/unsubscribe?t=", queued[0]["body"])
        self.assertIn("&p=gurugram%3ARERA-GRG-9001-2024", queued[0]["body"])
        link = re.search(r"https://tracker\.example\S+", queued[0]["body"].split("Stop these alerts")[1]).group(0)
        verified = tokens.verify(SECRET, "unsub", parse_qs(urlsplit(link).query)["t"][0])
        self.assertEqual(int(verified), subscriber["id"])

    def test_confirmation_mail_and_pages_in_hindi(self):
        sent = self.signup(email_lang="hi", query="?lang=hi")
        self.assertIn("अपना ईमेल देखें", sent.text)
        self.assertEqual(self.mail[0]["subject"], "SUNRISE HEIGHTS के अलर्ट की पुष्टि करें")
        self.assertIn("लिंक 7 दिन तक चलता है", self.mail[0]["body"])
        link = self.confirm_link()
        self.assertIn("lang=hi", link)
        self.assertIn("अलर्ट की पुष्टि करें", self.client.get(link).text)
        self.confirm(link)
        self.assertEqual(self.store.get_subscriber("email", "anita@example.com")["lang"], "hi")

    def test_a_form_sent_too_fast_or_too_late_or_forged_is_refused(self):
        token = self.form_token()
        for label, response in (
            ("too fast", self.signup(token, wait=0)),
            ("too late", self.signup(token, wait=3 * 3600)),
            ("forged", self.signup("abc.def", wait=5)),
            ("empty", self.signup("", wait=5)),
            ("other purpose", self.signup(tokens.sign(SECRET, "unsub", "1"), wait=5)),
        ):
            self.assertEqual(response.code, 400, label)
            self.assertIn("timed out or was sent too quickly", response.text, label)
            self.assertIn('value="anita@example.com"', response.text, label)
        self.assertEqual(self.mail, [])
        self.assertEqual(self.store.count_signups_since("anita@example.com", "2000-01-01T00:00:00Z"), 0)

    def test_a_filled_honeypot_looks_like_success_but_does_nothing(self):
        response = self.signup(website="http://spam.example")
        self.assertEqual(response.code, 200)
        self.assertIn("Check your email", response.text)
        self.assertEqual(self.mail, [])
        self.assertEqual(self.store.count_signups_since("anita@example.com", "2000-01-01T00:00:00Z"), 0)

    def test_bad_email_and_missing_consent_show_the_form_again(self):
        token = self.form_token()
        for bad in ("", "plain", "a@b", "a b@example.com", "a@@example.com", "<x>@example.com", "x@example", "x@.com",
                    "x@example..com", "a" * 300 + "@example.com"):
            response = self.signup(token, email=bad)
            self.assertEqual(response.code, 400, bad[:20])
            self.assertIn("valid email address", response.text, bad[:20])
        no_consent = self.signup(token, consent="")
        self.assertEqual(no_consent.code, 400)
        self.assertIn("tick the box", no_consent.text)
        self.assertEqual(self.mail, [])

    def test_unknown_project_in_the_form(self):
        self.assertEqual(self.signup(project_id="NO-SUCH").code, 404)
        self.assertEqual(self.signup(authority="delhi").code, 404)

    def test_one_address_cannot_be_used_to_flood_an_inbox(self):
        token = self.form_token()
        self.clock.advance(5)
        results = [self.signup(token, wait=1) for _ in range(5)]
        self.assertEqual({r.code for r in results}, {200})
        self.assertEqual(len(self.mail), 3, "only the first three requests per address per day send mail")
        self.clock.advance(25 * 3600)
        self.signup(self.form_token(), wait=5)
        self.assertEqual(len(self.mail), 4)

    def test_a_buyer_who_confirms_each_request_is_never_throttled(self):
        for n in range(1, 5):
            self.store.upsert_listed("gurugram", [{
                "key": "gurugram:P-%d" % n, "authority": "gurugram", "project_id": "P-%d" % n, "name": "TOWER %d" % n,
                "builder": "B", "location": "L", "district": "D", "valid_upto": "2030-01-01"}], "2026-11-19T00:00:00Z")
        for n in range(1, 5):
            self.signup(project_id="P-%d" % n)
            self.confirm()
        self.assertEqual(len(self.mail), 4, "four confirmed follows in one day must all get their email")
        self.assertEqual(len(self.store.subscriptions_of(self.store.get_subscriber("email", "anita@example.com")["id"])), 4)

    def test_already_subscribed_addresses_get_no_second_email_and_learn_nothing(self):
        self.subscribe_fully()
        before = len(self.mail)
        again = self.signup()
        self.assertEqual(again.code, 200)
        self.assertIn("Check your email", again.text)
        self.assertEqual(len(self.mail), before)

    def test_per_visitor_rate_limit(self):
        self.cfg.signups_per_ip_per_hour = 2
        app = web.create_app(self.cfg)
        self.client = Client(app, ip="198.51.100.9")
        token = self.form_token()
        self.clock.advance(5)
        codes = [self.signup(token, email="p%d@example.com" % i, wait=1).code for i in range(4)]
        self.assertEqual(codes, [200, 200, 429, 429])
        other = Client(app, ip="198.51.100.10")
        self.clock.advance(5)
        response = other.post("/subscribe", data={"authority": "gurugram", "project_id": "RERA-GRG-9001-2024", "ft": token,
                                                  "email": "q@example.com", "consent": "yes", "email_lang": "en"})
        self.assertEqual(response.code, 200)
        self.clock.advance(3600)
        self.assertEqual(self.signup(self.form_token(), email="r@example.com").code, 200)

    def test_proxy_header_is_trusted_only_when_asked(self):
        self.cfg.signups_per_ip_per_hour = 1
        for trust, expected in ((False, [200, 429]), (True, [200, 200])):
            self.cfg.trust_proxy = trust
            self.cfg.db_path = os.path.join(self.dir.name, "proxy-%s.db" % trust)
            app = web.create_app(self.cfg)
            seed = Store(self.cfg.db_path)
            Tracker(seed, HaryanaSource(self.site), today=date(2026, 11, 19), now=Clock()).sync("gurugram")
            seed.close()
            codes = []
            for i, forwarded in enumerate(("10.0.0.1", "10.0.0.2")):
                client = Client(app, ip="192.0.2.1")
                token = re.search(r'name="ft" value="([^"]+)"', client.get(PAGE).text).group(1)
                self.clock.advance(5)
                codes.append(client.post("/subscribe", data={
                    "authority": "gurugram", "project_id": "RERA-GRG-9001-2024", "ft": token, "email": "t%d@example.com" % i,
                    "consent": "yes", "email_lang": "en"}, extra={"HTTP_X_FORWARDED_FOR": forwarded}).code)
            self.assertEqual(codes, expected, trust)

    def test_a_mail_failure_leaves_nothing_behind_and_says_so(self):
        self.mail_error = DeliveryError("smtp down")
        response = self.signup()
        self.assertEqual(response.code, 503)
        self.assertIn("could not send the confirmation email", response.text)
        self.assertEqual(self.store.count_signups_since("anita@example.com", "2000-01-01T00:00:00Z"), 0)
        self.mail_error = None
        self.assertEqual(self.signup().code, 200)

    def test_confirmation_links_expire_and_cannot_be_forged_or_reused_for_other_things(self):
        self.signup()
        link = self.confirm_link()
        token = parse_qs(urlsplit(link).query)["t"][0]
        for label, bad in (("forged", "abc.def"), ("empty", ""), ("unsubscribe token", tokens.sign(SECRET, "unsub", "1"))):
            for response in (self.client.get("/confirm?t=" + bad), self.client.post("/confirm", data={"t": bad})):
                self.assertEqual(response.code, 400, label)
                self.assertIn("This link does not work", response.text, label)
        self.clock.advance(8 * 86400)
        late = self.client.post("/confirm", data={"t": token})
        self.assertEqual(late.code, 400)
        self.assertFalse(self.store.is_subscribed("email", "anita@example.com", KEY))

    def test_a_confirmation_link_for_a_deleted_request_is_dead(self):
        self.signup()
        link = self.confirm_link()
        self.store.purge_unconfirmed("2999-01-01T00:00:00Z")
        self.assertEqual(self.confirm(link).code, 400)

    def test_oversized_and_odd_requests(self):
        self.assertEqual(self.client.post("/subscribe", raw=b"x" * 20000).code, 413)
        self.assertEqual(self.client.post("/subscribe", raw=b"{}", content_type="application/json").code, 415)
        self.assertEqual(self.client.post("/subscribe", extra={"CONTENT_LENGTH": "abc"}).code, 400)


class UnsubscribeTest(WebCase):
    def setUp(self):
        super().setUp()
        self.track()
        self.subscribe_fully()
        self.subscriber = self.store.get_subscriber("email", "anita@example.com")["id"]

    def second_project(self):
        self.site.set_list([listing(valid="2027-06-30"), fx.list_row(2, "RERA-GRG-1-2019", "OLD TOWERS", "SLOW HOMES LTD",
                                                                      "30/06/2023", lapsed=True)])
        self.signup(project_id="RERA-GRG-1-2019")
        self.confirm()

    def test_the_stop_page_offers_this_project_and_everything(self):
        page = self.client.get(self.unsub_link(self.subscriber, "en", KEY))
        self.assertEqual(page.code, 200)
        self.assertIn("Stop alerts for SUNRISE HEIGHTS", page.text)
        self.assertIn("Stop all alerts and delete my data", page.text)
        only_all = self.client.get(self.unsub_link(self.subscriber, "en", None))
        self.assertNotIn("Stop alerts for", only_all.text)
        self.assertIn("Stop all alerts and delete my data", only_all.text)
        hindi = self.client.get(self.unsub_link(self.subscriber, "hi", KEY))
        self.assertIn("अलर्ट रोकें", hindi.text)
        self.assertTrue(self.store.is_subscribed("email", "anita@example.com", KEY), "opening the page must not unsubscribe")

    def test_stopping_the_only_project_erases_the_person(self):
        link = self.unsub_link(self.subscriber, "en", KEY)
        done = self.client.post(link, data={"action": "project", "p": KEY})
        self.assertIn("Alerts for SUNRISE HEIGHTS have stopped.", done.text)
        self.assertIsNone(self.store.get_subscriber_by_id(self.subscriber))
        self.assertEqual(self.store.count_signups_since("anita@example.com", "2000-01-01T00:00:00Z"), 0)
        self.assertEqual([m for m in self.store.pending_messages() if m["address"] == "anita@example.com"], [])
        self.assertIn("We hold no data about you", self.client.get(link).text)
        self.assertIn("We hold no data about you", self.client.post(link, data={"action": "all"}).text)

    def test_stopping_one_of_two_keeps_the_other(self):
        self.second_project()
        self.client.post(self.unsub_link(self.subscriber, "en", KEY), data={"action": "project", "p": KEY})
        self.assertEqual(self.store.subscriptions_of(self.subscriber), ["gurugram:RERA-GRG-1-2019"])
        self.assertIsNotNone(self.store.get_subscriber_by_id(self.subscriber))

    def test_stop_everything_erases_everything_about_the_person(self):
        self.second_project()
        done = self.client.post(self.unsub_link(self.subscriber), data={"action": "all"})
        self.assertIn("All alerts have stopped and your data has been deleted.", done.text)
        self.assertIsNone(self.store.get_subscriber_by_id(self.subscriber))
        self.assertEqual(self.store.subscriptions_of(self.subscriber), [])
        self.assertEqual(self.store.count_signups_since("anita@example.com", "2000-01-01T00:00:00Z"), 0)
        self.assertEqual([m for m in self.store.pending_messages() if m["address"] == "anita@example.com"], [])
        self.assertEqual(self.store.tracked_keys(), [KEY], "only the operator's own follow is left")

    def test_the_one_click_button_in_mail_apps(self):
        link = self.unsub_link(self.subscriber)
        response = self.client.post(link, data={"List-Unsubscribe": "One-Click"})
        self.assertEqual(response.code, 200)
        self.assertIsNone(self.store.get_subscriber_by_id(self.subscriber))

    def test_other_people_cannot_be_unsubscribed_with_my_link(self):
        other = self.store.add_subscriber("", "email", "someone@example.com", "en", "2026-11-19T00:00:00Z")
        self.store.subscribe(other, KEY, "2026-11-19T00:00:00Z")
        self.client.post(self.unsub_link(self.subscriber), data={"action": "all"})
        self.assertTrue(self.store.is_subscribed("email", "someone@example.com", KEY))

    def test_bad_links_and_bad_actions(self):
        for token in ("", "abc.def", tokens.sign(SECRET, "confirm", str(self.subscriber), expires_at=2 ** 40)):
            for response in (self.client.get("/unsubscribe?t=" + token), self.client.post("/unsubscribe?t=" + token, data={"action": "all"})):
                self.assertEqual(response.code, 400)
        link = self.unsub_link(self.subscriber)
        self.assertEqual(self.client.post(link, data={"action": "nonsense"}).code, 400)
        self.assertEqual(self.client.post(link, data={"action": "project"}).code, 400, "needs a project")
        self.assertEqual(self.client.post(link, data={"action": "project", "p": "x:y; DROP TABLE"}).code, 400)
        self.assertTrue(self.store.is_subscribed("email", "anita@example.com", KEY))

    def test_alert_emails_get_the_one_click_headers(self):
        self.tracker.unsubscribe_url = self.app.unsubscribe_url
        sent = []
        with mock.patch("rera_tracker.tracker.deliver", side_effect=lambda *a, **k: sent.append((a, k))):
            self.store.db.execute("UPDATE subscribers SET channel = 'email'")
            self.store.db.commit()
            self.tracker.send()
        self.assertTrue(sent)
        headers = sent[0][1]["headers"]
        self.assertTrue(headers["List-Unsubscribe"].startswith("<https://tracker.example/unsubscribe?t="))
        self.assertEqual(headers["List-Unsubscribe-Post"], "List-Unsubscribe=One-Click")
        self.assertNotIn("p=", headers["List-Unsubscribe"])


if __name__ == "__main__":
    unittest.main()
