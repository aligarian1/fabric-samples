"""A small website for the tracker: search, a public page for every project,
and email sign-up with double opt-in.  WSGI, standard library only.

Design rules
* Every piece of text from the database or the URL is HTML-escaped.
* No JavaScript and no cookies.  Forms carry a signed, time-stamped token.
* Nobody is emailed until they click a confirmation link (double opt-in).
* Every alert email carries a personal link that stops alerts and deletes data.
* Links in emails are built from the configured base URL, never from the
  request's Host header (which a stranger can fake).
"""
from __future__ import annotations

import html
import http
import json
import os
import re
import secrets
import sys
import threading
import time
import traceback
import urllib.parse
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Deque, Dict, List, Optional, Tuple

from . import tokens
from .clock import today_ist, utc_stamp
from .haryana import AUTHORITIES
from .messages import LANGS, Facts, facts, fmt_date
from .notify import DeliveryError, send_email
from .store import Store
from .tracker import Tracker, build_state
from .web_text import PRIVACY_VERSION, privacy_sections, tp

MAX_BODY = 16 * 1024
SEARCH_LIMIT = 25
_EMAIL = re.compile(r"^[^@\s<>\"'(),;:\\]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9.\-]{0,253}[A-Za-z0-9])?\.[A-Za-z]{2,}$")
_PROJECT_ID = re.compile(r"[A-Za-z0-9._\-]{1,80}")
_PROJECT_KEY = re.compile(r"(?:%s):[A-Za-z0-9._\-]{1,80}" % "|".join(sorted(AUTHORITIES)))
_AUTHORITY_NAMES = {"gurugram": "Gurugram", "panchkula": "Panchkula"}

_SECURITY_HEADERS = [
    (
        "Content-Security-Policy",
        "default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; form-action 'self'; "
        "base-uri 'none'; frame-ancestors 'none'",
    ),
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
    ("Permissions-Policy", "geolocation=(), camera=(), microphone=()"),
]

_CSS = """
:root{--bg:#fff;--fg:#1b1f23;--muted:#58636e;--card:#f6f8fa;--line:#d0d7de;--accent:#0b5cad;--warn:#7a4200;--warnbg:#fff4e5;--ok:#17642d}
@media (prefers-color-scheme:dark){:root{--bg:#0f1317;--fg:#e6edf3;--muted:#9aa7b3;--card:#171c22;--line:#2d353d;--accent:#6cb2ff;--warn:#f0b35a;--warnbg:#2a2113;--ok:#6fd58a}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 system-ui,-apple-system,"Segoe UI","Noto Sans","Noto Sans Devanagari",sans-serif}
a{color:var(--accent)}
header,main,footer{max-width:46rem;margin:0 auto;padding:0 1rem}
header{display:flex;justify-content:space-between;align-items:center;gap:1rem;flex-wrap:wrap;padding-top:1rem;padding-bottom:.5rem}
header nav{display:flex;gap:1rem;align-items:center}
.brand{font-weight:700;text-decoration:none;color:var(--fg)}
h1{font-size:1.6rem;line-height:1.25;margin:.75rem 0 .25rem}
h2{font-size:1.15rem;margin:1.5rem 0 .5rem}
.sub,.muted,.note,.asof{color:var(--muted)}
.sub{margin:0 0 .75rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:.5rem;padding:1rem;margin:1rem 0}
.card>:first-child{margin-top:0}.card>:last-child{margin-bottom:0}
.facts{display:grid;grid-template-columns:minmax(9rem,max-content) 1fr;gap:.4rem 1rem;background:var(--card);border:1px solid var(--line);border-radius:.5rem;padding:1rem;margin:1rem 0}
.facts dt{color:var(--muted)}.facts dd{margin:0;overflow-wrap:anywhere}
.warn{background:var(--warnbg);color:var(--warn);border-radius:.4rem;padding:.6rem .8rem}
.err{border:1px solid var(--warn);background:var(--warnbg);color:var(--warn);border-radius:.4rem;padding:.6rem .8rem;margin:1rem 0}
ul.plain{list-style:none;padding:0;margin:0}
ul.plain li{padding:.6rem 0;border-bottom:1px solid var(--line)}
form label{display:block;margin:.75rem 0 .25rem;font-weight:600}
form label.check{font-weight:400;display:flex;gap:.6rem;align-items:flex-start}
input[type=email],input[type=search],input[type=text],select{width:100%;min-height:2.75rem;padding:.5rem .7rem;font:inherit;color:var(--fg);background:var(--bg);border:1px solid var(--line);border-radius:.4rem}
input[type=checkbox]{margin-top:.35rem;width:1.1rem;height:1.1rem;flex:none}
button{min-height:2.75rem;padding:.5rem 1.1rem;font:inherit;font-weight:600;color:#fff;background:var(--accent);border:0;border-radius:.4rem;cursor:pointer;margin-top:1rem}
@media (prefers-color-scheme:dark){button{color:#0f1317}}
button.quiet{background:transparent;color:var(--accent);border:1px solid var(--accent)}
.row{display:flex;gap:.5rem}.row input{flex:1}.row button{margin-top:0}
.hp{position:absolute;left:-10000px;width:1px;height:1px;overflow:hidden}
footer{padding-top:1rem;padding-bottom:2rem;font-size:.9rem;color:var(--muted)}
@media (max-width:34rem){.facts{grid-template-columns:1fr}.facts dt{margin-top:.5rem}.row{flex-direction:column}}
"""


class ConfigError(Exception):
    """The website is not configured well enough to run in public."""


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _t(lang: str, key: str, **values: object) -> str:
    """Escaped website text."""
    return _e(tp(lang, key, **values))


def _href(path: str, lang: str = "en", **params: Optional[str]) -> str:
    query = {k: v for k, v in params.items() if v not in (None, "")}
    if lang != "en":
        query["lang"] = lang
    return path + ("?" + urllib.parse.urlencode(query) if query else "")


@dataclass
class WebConfig:
    db_path: str = "rera_tracker.db"
    secret: str = ""
    base_url: str = ""
    business_name: str = ""
    contact_email: str = ""
    trust_proxy: bool = False
    min_form_seconds: float = 3.0
    max_form_seconds: float = 7200.0
    confirm_days: int = 7
    signups_per_email_per_day: int = 3
    signups_per_ip_per_hour: int = 20
    stale_hours: float = 36.0
    sender: Optional[Callable[[str, str, str, Optional[Dict[str, str]]], None]] = None
    clock: Callable[[], float] = time.time

    @classmethod
    def from_env(cls) -> "WebConfig":
        env = os.environ.get
        return cls(
            db_path=env("RERA_TRACKER_DB", "rera_tracker.db"),
            secret=env("RERA_TRACKER_SECRET", ""),
            base_url=env("RERA_TRACKER_BASE_URL", "").rstrip("/"),
            business_name=env("RERA_TRACKER_BUSINESS_NAME", ""),
            contact_email=env("RERA_TRACKER_CONTACT_EMAIL", ""),
            trust_proxy=env("RERA_TRACKER_TRUST_PROXY", "") == "1",
        )

    def problems(self) -> List[str]:
        found = []
        if len(self.secret) < 16:
            found.append("RERA_TRACKER_SECRET must be a long random value (at least 16 characters)")
        local = self.base_url.startswith(("http://127.0.0.1", "http://localhost"))
        if not (self.base_url.startswith("https://") or local):
            found.append("RERA_TRACKER_BASE_URL must be the public https:// address of the site")
        if not self.business_name:
            found.append("RERA_TRACKER_BUSINESS_NAME is needed for the privacy notice")
        if not self.contact_email:
            found.append("RERA_TRACKER_CONTACT_EMAIL is needed for the privacy notice")
        return found


def make_unsubscribe_url(base_url: str, secret: str) -> Callable[[int, str, Optional[str]], str]:
    """Build personal "stop alerts" links: (subscriber id, language, project key) -> URL."""

    def build(subscriber_id: int, lang: str, project_key: Optional[str] = None) -> str:
        params: Dict[str, str] = {"t": tokens.sign(secret, "unsub", str(subscriber_id))}
        if project_key:
            params["p"] = project_key
        if lang in LANGS and lang != "en":
            params["lang"] = lang
        return base_url.rstrip("/") + "/unsubscribe?" + urllib.parse.urlencode(params)

    return build


class RateLimiter:
    """At most ``limit`` hits per ``window`` seconds for each key (per process)."""

    def __init__(self, limit: int, window: float, clock: Callable[[], float]) -> None:
        self.limit, self.window, self.clock = limit, window, clock
        self._hits: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = self.clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            if len(self._hits) > 10000:
                self._hits = {k: v for k, v in self._hits.items() if v}
            return True


def _first_values(raw: str) -> Dict[str, str]:
    try:
        parsed = urllib.parse.parse_qs(raw, keep_blank_values=True, max_num_fields=30)
    except ValueError:
        return {}
    return {key: values[0][:500] for key, values in parsed.items() if values}


class Request:
    def __init__(self, environ: dict, cfg: WebConfig, store: Store) -> None:
        self.environ = environ
        self.cfg = cfg
        self.store = store
        self.method = environ.get("REQUEST_METHOD", "GET").upper()
        self.path = environ.get("PATH_INFO") or "/"
        self.query = _first_values(environ.get("QUERY_STRING", ""))
        self.form: Dict[str, str] = {}
        self.lang = self.query.get("lang") if self.query.get("lang") in LANGS else "en"
        remote = environ.get("REMOTE_ADDR", "")
        if cfg.trust_proxy and environ.get("HTTP_X_FORWARDED_FOR"):
            remote = environ["HTTP_X_FORWARDED_FOR"].split(",")[0].strip()
        self.ip = remote[:64]
        self.body_status = 0  # non-zero when the body was refused

    def read_form(self) -> None:
        try:
            length = int(self.environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            self.body_status = 400
            return
        if length > MAX_BODY or length < 0:
            self.body_status = 413
            return
        if not (self.environ.get("CONTENT_TYPE", "").split(";")[0].strip().lower() == "application/x-www-form-urlencoded"):
            self.body_status = 415
            return
        raw = self.environ["wsgi.input"].read(length) if length else b""
        self.form = _first_values(raw.decode("utf-8", "replace"))


class Response:
    def __init__(self, body: str = "", status: int = 200, content_type: str = "text/html; charset=utf-8",
                 cache: bool = False, headers: Optional[List[Tuple[str, str]]] = None) -> None:
        self.status = status
        self.body = body.encode("utf-8")
        self.headers: List[Tuple[str, str]] = [
            ("Content-Type", content_type),
            ("Cache-Control", "public, max-age=300" if cache else "no-store"),
        ] + (headers or [])


class App:
    def __init__(self, cfg: WebConfig) -> None:
        problems = cfg.problems()
        if problems:
            raise ConfigError("; ".join(problems))
        self.cfg = cfg
        self.unsubscribe_url = make_unsubscribe_url(cfg.base_url, cfg.secret)
        self.sender = cfg.sender or send_email
        self.ip_limit = RateLimiter(cfg.signups_per_ip_per_hour, 3600, cfg.clock)
        Store(cfg.db_path).close()  # create tables once; requests open the file without re-checking
        self.https = cfg.base_url.startswith("https://")

    # -- WSGI ------------------------------------------------------------------
    def __call__(self, environ: dict, start_response: Callable) -> List[bytes]:
        store = Store(self.cfg.db_path, init=False)
        try:
            req = Request(environ, self.cfg, store)
            try:
                response = self.route(req)
            except Exception:  # noqa: BLE001 - a bug must show a calm page, not a stack trace
                environ["wsgi.errors"].write(traceback.format_exc())
                response = self.message(req.lang, "error_h", "error_p", status=500)
        finally:
            store.close()
        headers = response.headers + _SECURITY_HEADERS
        if self.https:
            headers.append(("Strict-Transport-Security", "max-age=31536000"))
        body = b"" if environ.get("REQUEST_METHOD", "").upper() == "HEAD" else response.body
        headers.append(("Content-Length", str(len(response.body))))
        status = "%d %s" % (response.status, http.HTTPStatus(response.status).phrase)
        start_response(status, headers)
        return [body]

    # -- helpers ---------------------------------------------------------------
    def now(self) -> float:
        return self.cfg.clock()

    def today(self):
        return today_ist(datetime.fromtimestamp(self.now(), timezone.utc))

    def page(self, lang: str, title: str, body: str, *, description: str = "", canonical: Optional[str] = None,
             alternates: Optional[Dict[str, str]] = None, switch_href: str = "/", noindex: bool = False,
             status: int = 200, cache: bool = False) -> Response:
        other = "hi" if lang == "en" else "en"
        head = [
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            "<title>%s</title>" % _e("%s – %s" % (title, tp(lang, "site"))),
        ]
        if description:
            head.append('<meta name="description" content="%s">' % _e(description[:300]))
        if noindex:
            head.append('<meta name="robots" content="noindex">')
        if canonical:
            head.append('<link rel="canonical" href="%s">' % _e(canonical))
        for code, url in (alternates or {}).items():
            head.append('<link rel="alternate" hreflang="%s" href="%s">' % (_e(code), _e(url)))
        head.append("<style>%s</style>" % _CSS)
        document = (
            '<!doctype html><html lang="%s"><head>%s</head><body>'
            '<header><a class="brand" href="%s">%s</a><nav><a href="%s">%s</a><a href="%s" lang="%s">%s</a></nav></header>'
            "<main>%s</main>"
            "<footer><p>%s</p></footer></body></html>"
        ) % (
            _e(lang), "".join(head), _e(_href("/", lang)), _t(lang, "site"),
            _e(_href("/privacy", lang)), _t(lang, "nav_privacy"),
            _e(switch_href), other, _t(lang, "lang_switch"),
            body, _t(lang, "indep"),
        )
        return Response(document, status=status, cache=cache)

    def message(self, lang: str, heading_key: str, text_key: str, status: int = 200, **values: object) -> Response:
        body = '<h1>%s</h1><p>%s</p><p><a href="%s">%s</a></p>' % (
            _t(lang, heading_key, **values), _t(lang, text_key, **values), _e(_href("/", lang)), _t(lang, "home_link"),
        )
        return self.page(lang, tp(lang, heading_key, **values), body, noindex=True, status=status)

    def not_found(self, req: Request) -> Response:
        return self.message(req.lang, "notfound_h", "notfound_p", status=404)

    @staticmethod
    def method_not_allowed(allowed: str) -> Response:
        return Response("Method not allowed", status=405, content_type="text/plain; charset=utf-8",
                        headers=[("Allow", allowed)])

    # -- routing ---------------------------------------------------------------
    def route(self, req: Request) -> Response:
        path, method = req.path, req.method
        if method == "HEAD":
            method = "GET"
        match = re.fullmatch(r"/p/(%s)/(%s)" % ("|".join(sorted(AUTHORITIES)), _PROJECT_ID.pattern), path)
        routes = {
            "/": ("GET", self.home),
            "/search": ("GET", self.search),
            "/privacy": ("GET", self.privacy),
            "/subscribe": ("POST", self.subscribe),
            "/confirm": ("GET POST", self.confirm),
            "/unsubscribe": ("GET POST", self.unsubscribe),
            "/health": ("GET", self.health),
            "/robots.txt": ("GET", self.robots),
            "/sitemap.xml": ("GET", self.sitemap),
        }
        if match:
            if method != "GET":
                return self.method_not_allowed("GET, HEAD")
            return self.project_page(req, match.group(1), match.group(2))
        if path not in routes:
            return self.not_found(req)
        allowed, handler = routes[path]
        if method not in allowed.split():
            return self.method_not_allowed(allowed.replace("GET", "GET, HEAD") if "GET" in allowed else allowed)
        if method == "POST":
            req.read_form()
            if req.body_status:
                return Response("Request refused", status=req.body_status, content_type="text/plain; charset=utf-8")
        return handler(req)

    # -- simple pages ----------------------------------------------------------
    def home(self, req: Request) -> Response:
        lang, store = req.lang, req.store
        last = store.last_sync()
        count = store.count_projects()
        covers = (
            _t(lang, "covers", n="{:,}".format(count), date=fmt_date(last[:10], lang))
            if last else _t(lang, "covers_nodate", n="{:,}".format(count))
        )
        body = (
            "<h1>%s</h1><p>%s</p>%s<p class=\"muted\">%s</p>"
        ) % (_t(lang, "home_h"), _t(lang, "home_p"), self.search_form(lang, ""), covers)
        return self.page(
            lang, tp(lang, "tagline"), body, description=tp(lang, "home_p"),
            canonical=self.cfg.base_url + _href("/", lang),
            alternates={"en": self.cfg.base_url + "/", "hi": self.cfg.base_url + "/?lang=hi"},
            switch_href=_href("/", "hi" if lang == "en" else "en"), cache=True,
        )

    @staticmethod
    def search_form(lang: str, query: str) -> str:
        hidden = '<input type="hidden" name="lang" value="%s">' % _e(lang) if lang != "en" else ""
        return (
            '<form action="/search" method="get" role="search" class="card"><label for="q">%s</label>'
            '<div class="row"><input id="q" name="q" type="search" value="%s" placeholder="%s" maxlength="100" '
            'autocomplete="off" required>%s<button type="submit">%s</button></div></form>'
        ) % (_t(lang, "search_label"), _e(query), _t(lang, "search_ph"), hidden, _t(lang, "search_btn"))

    def search(self, req: Request) -> Response:
        lang = req.lang
        query = req.query.get("q", "").strip()[:100]
        parts = [self.search_form(lang, query)]
        if len(query) < 2:
            parts.append("<p>%s</p>" % _t(lang, "results_short"))
        else:
            found = req.store.find_projects(query, limit=SEARCH_LIMIT + 1)
            parts.append("<h1>%s</h1>" % _t(lang, "results_h", q=query))
            if not found:
                parts.append("<p>%s</p>" % _t(lang, "results_none"))
            else:
                items = []
                for project in found[:SEARCH_LIMIT]:
                    listed = project["listed"]
                    notes = []
                    if listed.get("valid_upto"):
                        notes.append(tp(lang, "valid_to", date=fmt_date(listed["valid_upto"], lang)))
                    if listed.get("lapsed"):
                        notes.append(tp(lang, "lapsed_tag"))
                    detail = " · ".join(x for x in (project["builder"], project["location"], ", ".join(notes)) if x)
                    link = _href("/p/%s/%s" % (project["authority"], project["project_id"]), lang)
                    items.append('<li><a href="%s">%s</a><br><span class="muted">%s</span></li>' % (
                        _e(link), _e(project["name"] or project["project_id"]), _e(detail)))
                parts.append('<ul class="plain">%s</ul>' % "".join(items))
                if len(found) > SEARCH_LIMIT:
                    parts.append('<p class="muted">%s</p>' % _t(lang, "results_more", n=SEARCH_LIMIT))
        return self.page(lang, tp(lang, "search_btn"), "".join(parts), noindex=True,
                         switch_href=_href("/search", "hi" if lang == "en" else "en", q=query))

    def privacy(self, req: Request) -> Response:
        lang = req.lang
        sections = privacy_sections(
            lang, business=self.cfg.business_name, contact=self.cfg.contact_email, days=self.cfg.confirm_days
        )
        body = "<h1>%s</h1>%s<p class=\"muted\">%s</p>" % (
            _t(lang, "privacy_h"),
            "".join("<h2>%s</h2><p>%s</p>" % (_e(h), _e(p)) for h, p in sections),
            _e(PRIVACY_VERSION),
        )
        return self.page(lang, tp(lang, "privacy_h"), body, canonical=self.cfg.base_url + _href("/privacy", lang),
                         switch_href=_href("/privacy", "hi" if lang == "en" else "en"), cache=True)

    def robots(self, req: Request) -> Response:
        text = "User-agent: *\nDisallow: /search\nDisallow: /subscribe\nDisallow: /confirm\nDisallow: /unsubscribe\n"
        text += "Sitemap: %s/sitemap.xml\n" % self.cfg.base_url
        return Response(text, content_type="text/plain; charset=utf-8", cache=True)

    def sitemap(self, req: Request) -> Response:
        urls = [self.cfg.base_url + "/"] + [
            "%s/p/%s/%s" % (self.cfg.base_url, a, p) for a, p in req.store.project_refs()
        ]
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n%s</urlset>\n' % "".join(
            "<url><loc>%s</loc></url>\n" % _e(url) for url in urls)
        return Response(xml, content_type="application/xml; charset=utf-8", cache=True)

    def health(self, req: Request) -> Response:
        store = req.store
        last_run = store.get_meta("last_run_at")
        problems = int(store.get_meta("last_run_problems") or 0)
        stale = False
        if last_run:
            age = self.now() - datetime.strptime(last_run, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
            stale = age > self.cfg.stale_hours * 3600
        payload = {
            "ok": not stale,
            "projects": store.count_projects(),
            "last_sync": store.last_sync(),
            "last_run": last_run,
            "last_run_problems": problems,
            "stale": stale,
        }
        return Response(json.dumps(payload), status=503 if stale else 200, content_type="application/json")

    # -- project page ----------------------------------------------------------
    def project_page(self, req: Request, authority: str, project_id: str, error: Optional[str] = None,
                     email: str = "", status: int = 200) -> Response:
        lang = req.lang
        project = req.store.get_project("%s:%s" % (authority, project_id))
        if project is None:
            return self.not_found(req)
        state = project["state"] or build_state(project["listed"], project["in_list"], None, None, None, None)
        f = facts(state, self.today(), lang)
        path = "/p/%s/%s" % (authority, project_id)
        stamp = project["state_at"] or project["last_seen"]
        as_of = fmt_date(stamp[:10], lang) if stamp else ""

        parts = ["<h1>%s</h1>" % _e(state.get("name") or project_id)]
        if state.get("builder"):
            parts.append('<p class="sub">%s</p>' % _e(state["builder"]))
        parts.append(self.facts_html(f))
        if as_of:
            parts.append('<p class="asof">%s</p>' % _t(lang, "asof" if project["state"] else "asof_list", date=as_of))
        parts.append('<p><a href="%s" rel="noopener noreferrer nofollow">%s</a></p>' % (_e(f.page_url), _t(lang, "official")))
        parts.append(self.signup_form(req, authority, project_id, error, email))
        title = state.get("name") or project_id
        description = " ".join(f"{label}: {value}." for label, value in f.rows[:6])
        return self.page(
            lang, title, "".join(parts), description=description,
            canonical=self.cfg.base_url + _href(path, lang),
            alternates={"en": self.cfg.base_url + path, "hi": self.cfg.base_url + path + "?lang=hi"},
            switch_href=_href(path, "hi" if lang == "en" else "en"), status=status, cache=(error is None),
        )

    @staticmethod
    def facts_html(f: Facts) -> str:
        out = ['<dl class="facts">%s</dl>' % "".join("<dt>%s</dt><dd>%s</dd>" % (_e(k), _e(v)) for k, v in f.rows)]
        if f.reports is not None:
            block = ['<div class="card"><p><strong>%s</strong></p>' % _e(f.reports)]
            if f.latest:
                block.append("<p>%s</p>" % _e(f.latest))
            if f.report_lines:
                block.append("<ul>%s</ul>" % "".join("<li>%s</li>" % _e(line) for line in f.report_lines))
            block.extend('<p class="warn">%s</p>' % _e(w) for w in f.warnings)
            block.append("</div>")
            out.append("".join(block))
        if f.hearings:
            items = "".join("<li><strong>%s</strong> — %s<br>%s</li>" % (_e(d), _e(s), _e(t)) for d, s, t in f.hearings)
            out.append("<h2>%s</h2><ul>%s</ul>" % (_e(f.hearings_label), items))
        return "".join(out)

    def signup_form(self, req: Request, authority: str, project_id: str, error: Optional[str], email: str) -> str:
        lang = req.lang
        token = tokens.sign(self.cfg.secret, "form", str(int(self.now())))
        selected = lambda code: " selected" if code == lang else ""  # noqa: E731
        banner = '<p class="err" role="alert">%s</p>' % _t(lang, error) if error else ""
        return (
            '<section id="alerts"><h2>%s</h2>%s<form method="post" action="%s" class="card">'
            '<input type="hidden" name="authority" value="%s"><input type="hidden" name="project_id" value="%s">'
            '<input type="hidden" name="ft" value="%s">'
            '<div class="hp" aria-hidden="true"><label>Website<input type="text" name="website" tabindex="-1" autocomplete="off"></label></div>'
            '<label for="email">%s</label><input id="email" name="email" type="email" inputmode="email" autocomplete="email" '
            'maxlength="254" required value="%s">'
            '<label for="elang">%s</label><select id="elang" name="email_lang"><option value="en"%s>English</option>'
            '<option value="hi"%s>हिन्दी</option></select>'
            '<label class="check"><input type="checkbox" name="consent" value="yes" required><span>%s <a href="%s">%s</a></span></label>'
            '<button type="submit">%s</button><p class="note">%s</p></form></section>'
        ) % (
            _t(lang, "alerts_h"), banner, _e(_href("/subscribe", lang)), _e(authority), _e(project_id), _e(token),
            _t(lang, "email"), _e(email), _t(lang, "language"), selected("en"), selected("hi"),
            _t(lang, "consent", business=self.cfg.business_name), _e(_href("/privacy", lang)), _t(lang, "privacy_link"),
            _t(lang, "submit"), _t(lang, "form_note"),
        )

    # -- sign-up ---------------------------------------------------------------
    def sent_page(self, lang: str) -> Response:
        return self.message(lang, "sent_h", "sent_p", days=self.cfg.confirm_days)

    def subscribe(self, req: Request) -> Response:
        form, lang, store = req.form, req.lang, req.store
        authority, project_id = form.get("authority", ""), form.get("project_id", "")
        if authority not in AUTHORITIES or not _PROJECT_ID.fullmatch(project_id):
            return self.not_found(req)
        project = store.get_project("%s:%s" % (authority, project_id))
        if project is None:
            return self.not_found(req)
        email_text = form.get("email", "").strip()

        def again(error: str, status: int = 400) -> Response:
            return self.project_page(req, authority, project_id, error=error, email=email_text, status=status)

        try:
            issued = int(tokens.verify(self.cfg.secret, "form", form.get("ft", ""), now=self.now()))
        except (tokens.TokenError, ValueError):
            return again("err_form")
        age = self.now() - issued
        if age < self.cfg.min_form_seconds or age > self.cfg.max_form_seconds:
            return again("err_form")
        if form.get("website"):  # a field only a script fills in: pretend it worked
            return self.sent_page(lang)
        if not self.ip_limit.allow(req.ip or "unknown"):
            return again("err_limit", status=429)
        if not _EMAIL.fullmatch(email_text) or len(email_text) > 254:
            return again("err_email")
        if form.get("consent") != "yes":
            return again("err_consent")
        email = email_text.lower()
        email_lang = form.get("email_lang") if form.get("email_lang") in LANGS else lang

        # From here on every outcome looks the same to the visitor, so the form cannot be used to
        # discover who is already subscribed or to flood somebody's inbox.  Only requests that were
        # never confirmed count: they are the ones that can pester a stranger.
        since = utc_stamp(self.now() - 86400)
        if store.count_signups_since(email, since, unconfirmed_only=True) >= self.cfg.signups_per_email_per_day:
            return self.sent_page(lang)
        key = "%s:%s" % (authority, project_id)
        if store.is_subscribed("email", email, key):
            return self.sent_page(lang)

        signup_id = store.create_signup(email, email_lang, key, PRIVACY_VERSION, utc_stamp(self.now()))
        expires = int(self.now()) + self.cfg.confirm_days * 86400
        link = self.cfg.base_url + _href(
            "/confirm", email_lang, t=tokens.sign(self.cfg.secret, "confirm", str(signup_id), expires_at=expires)
        )
        values = dict(
            project=project["name"] or project_id, builder=project["builder"] or "-", site=tp(email_lang, "site"),
            url=link, days=self.cfg.confirm_days, business=self.cfg.business_name,
        )
        try:
            self.sender(email, tp(email_lang, "mail_confirm_subject", **values), tp(email_lang, "mail_confirm_body", **values), None)
        except (DeliveryError, OSError):
            store.delete_signup(signup_id)
            return again("err_mail", status=503)
        return self.sent_page(lang)

    def confirm(self, req: Request) -> Response:
        lang = req.lang
        token = req.form.get("t") or req.query.get("t", "")
        try:
            signup_id = int(tokens.verify(self.cfg.secret, "confirm", token, now=self.now()))
        except (tokens.TokenError, ValueError):
            return self.message(lang, "link_bad_h", "link_bad_p", status=400)
        signup = req.store.get_signup(signup_id)
        if signup is None:
            return self.message(lang, "link_bad_h", "link_bad_p", status=400)
        project = req.store.get_project(signup["project_key"])
        name = (project["name"] if project else None) or signup["project_key"]
        if req.method == "POST":
            if signup["confirmed_at"] is None:
                tracker = Tracker(req.store, None, today=self.today(), now=lambda: utc_stamp(self.now()),
                                  unsubscribe_url=self.unsubscribe_url)
                subscriber_id = tracker.subscribe(signup["project_key"], "", "email", signup["email"], signup["lang"])
                req.store.confirm_signup(signup_id, subscriber_id, utc_stamp(self.now()))
            return self.message(lang, "confirmed_h", "confirmed_p")
        # A plain visit only shows a button, so mail scanners that open links cannot confirm for anyone.
        body = (
            '<h1>%s</h1><p>%s</p><form method="post" action="%s"><input type="hidden" name="t" value="%s">'
            '<button type="submit">%s</button></form>'
        ) % (_t(lang, "confirm_h"), _t(lang, "confirm_p", project=name), _e(_href("/confirm", lang)),
             _e(token), _t(lang, "confirm_btn"))
        return self.page(lang, tp(lang, "confirm_h"), body, noindex=True)

    def unsubscribe(self, req: Request) -> Response:
        lang, store = req.lang, req.store
        token = req.query.get("t") or req.form.get("t", "")
        try:
            subscriber_id = int(tokens.verify(self.cfg.secret, "unsub", token))
        except (tokens.TokenError, ValueError):
            return self.message(lang, "link_bad_h", "link_bad_p", status=400)
        project_key = req.query.get("p") or req.form.get("p") or ""
        if project_key and not _PROJECT_KEY.fullmatch(project_key):
            project_key = ""
        subscriber = store.get_subscriber_by_id(subscriber_id)
        if req.method == "POST":
            if subscriber is None:
                return self.message(lang, "unsub_h", "unsub_nothing")
            one_click = req.form.get("List-Unsubscribe") == "One-Click"
            action = "all" if one_click else req.form.get("action", "")
            if action == "project" and project_key:
                project = store.get_project(project_key)
                store.stop_project(subscriber_id, project_key)
                return self.message(lang, "unsub_h", "unsub_done_project",
                                    project=(project["name"] if project else None) or project_key)
            if action == "all":
                store.delete_subscriber(subscriber_id)
                return self.message(lang, "unsub_h", "unsub_done_all")
            return self.message(lang, "link_bad_h", "link_bad_p", status=400)
        if subscriber is None:
            return self.message(lang, "unsub_h", "unsub_nothing")
        action_url = _e(_href("/unsubscribe", lang, t=token))
        buttons = []
        if project_key and project_key in store.subscriptions_of(subscriber_id):
            project = store.get_project(project_key)
            buttons.append(
                '<form method="post" action="%s"><input type="hidden" name="action" value="project">'
                '<input type="hidden" name="p" value="%s"><button type="submit" class="quiet">%s</button></form>'
                % (action_url, _e(project_key), _t(lang, "unsub_project", project=(project["name"] if project else None) or project_key))
            )
        buttons.append(
            '<form method="post" action="%s"><input type="hidden" name="action" value="all">'
            '<button type="submit">%s</button></form>' % (action_url, _t(lang, "unsub_all"))
        )
        body = "<h1>%s</h1><p>%s</p>%s" % (_t(lang, "unsub_h"), _t(lang, "unsub_p"), "".join(buttons))
        return self.page(lang, tp(lang, "unsub_h"), body, noindex=True)


def create_app(config: Optional[WebConfig] = None) -> App:
    """The WSGI application.  With no argument, settings come from the environment."""
    return App(config or WebConfig.from_env())


def serve(config: WebConfig, host: str = "127.0.0.1", port: int = 8080, print_mail: bool = False) -> None:
    """Run a development server.  For real traffic, put the app behind gunicorn and a reverse proxy."""
    from wsgiref.simple_server import WSGIRequestHandler, make_server

    if print_mail:
        def show(to: str, subject: str, body: str, headers: Optional[Dict[str, str]] = None) -> None:
            print("\n--- email to %s ---\nSubject: %s\n\n%s\n---" % (to, subject, body), flush=True)

        config.sender = show

    class QuietHandler(WSGIRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:  # never log query strings: they hold tokens
            sys.stderr.write("%s - %s\n" % (self.client_address[0], re.sub(r"\?\S*", "?…", fmt % args)))

    app = create_app(config)
    with make_server(host, port, app, handler_class=QuietHandler) as server:
        print("Serving on http://%s:%d  (Ctrl-C to stop)" % (host, port), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


def dev_config(base: WebConfig, port: int) -> WebConfig:
    """Fill in harmless values for local testing so the site can start."""
    base.secret = base.secret or secrets.token_urlsafe(32)
    base.base_url = base.base_url or "http://127.0.0.1:%d" % port
    base.business_name = base.business_name or "Demo Co (not a real service)"
    base.contact_email = base.contact_email or "demo@example.invalid"
    return base
