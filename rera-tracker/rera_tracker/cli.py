"""Command line for the tracker.  Run ``python -m rera_tracker --help``."""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from . import web
from .fetch import DEFAULT_DELAY, FetchError, PoliteFetcher
from .haryana import AUTHORITIES, HaryanaSource, ParseError
from .messages import LANGS, fmt_date
from .notify import CHANNELS, DeliveryError, send_email
from .store import Store
from .tracker import Tracker

CONFIRM_DAYS = 7


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rera_tracker",
        description="Watch public Haryana RERA records and tell flat buyers what changed.",
    )
    parser.add_argument("--db", default=os.environ.get("RERA_TRACKER_DB", "rera_tracker.db"), help="SQLite file (default: %(default)s)")
    parser.add_argument("--delay", type=float, default=float(os.environ.get("RERA_TRACKER_DELAY", DEFAULT_DELAY)),
                        help="seconds to wait between requests (default: %(default)s)")
    parser.add_argument("--max-requests", type=int, default=int(os.environ.get("RERA_TRACKER_MAX_REQUESTS", "500")),
                        help="hard cap on requests in one run (default: %(default)s)")
    parser.add_argument("--today", help="pretend today is this date (YYYY-MM-DD); for testing")
    sub = parser.add_subparsers(dest="command", required=True)

    sync = sub.add_parser("sync", help="download the registered-projects list")
    sync.add_argument("authority", choices=sorted(AUTHORITIES) + ["all"])

    stats = sub.add_parser("stats", help="count lapsed and expiring projects in the stored list")
    stats.add_argument("authority", nargs="?", choices=sorted(AUTHORITIES))

    find = sub.add_parser("find", help="search the stored list by project, builder or place")
    find.add_argument("text")

    subscribe = sub.add_parser("subscribe", help="start sending a person alerts for a project")
    subscribe.add_argument("project", help="project ID such as RERA-GRG-1817-2024")
    subscribe.add_argument("--name", required=True)
    subscribe.add_argument("--channel", choices=CHANNELS, default="console")
    subscribe.add_argument("--address", required=True, help="email address, phone number or any label")
    subscribe.add_argument("--lang", choices=LANGS, default="en")

    check = sub.add_parser("check", help="read tracked projects and queue messages for what changed")
    check.add_argument("project", nargs="?", help="check only this project")

    send = sub.add_parser("send", help="deliver queued messages")
    send.add_argument("--outbox", default="outbox", help="folder for the 'file' channel (default: %(default)s)")

    report = sub.add_parser("report", help="print a plain-language status report for a project")
    report.add_argument("project")
    report.add_argument("--lang", choices=LANGS, default="en")
    report.add_argument("--refresh", action="store_true", help="read the site again first")

    run = sub.add_parser("run", help="daily job: sync both lists, check tracked projects, send messages")
    run.add_argument("--outbox", default="outbox")

    serve = sub.add_parser("serve", help="run the website (development server; see README for real hosting)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)
    serve.add_argument("--dev", action="store_true",
                       help="fill in harmless settings and print confirmation emails instead of sending them")
    return parser


def _resolve(store: Store, ref: str) -> str:
    matches = store.resolve(ref)
    if not matches:
        raise SystemExit("No stored project matches %r. Run 'sync' first, or use 'find' to look it up." % ref)
    if len(matches) > 1:
        raise SystemExit("%r matches several projects: %s" % (ref, ", ".join(m["key"] for m in matches)))
    return matches[0]["key"]


def _print_check(result: dict) -> None:
    kinds = ", ".join(e.kind + (" (noted)" if e.silent else "") for e in result["events"]) or "nothing new"
    print("%s: %s; %d message(s) queued" % (result["key"], kinds, result["queued"]))
    for problem in result["problems"]:
        print("  could not read %s" % problem)


def _daily_run(store: Store, tracker: Tracker, outbox: str) -> int:
    """Sync both lists, check every followed project, send, tidy up, and record how it went."""
    problems: List[str] = []
    for authority in sorted(AUTHORITIES):
        try:
            counts = tracker.sync(authority)
            print("%s: %d projects (%d new)" % (authority, counts["total"], counts["new"]))
        except (FetchError, ParseError) as error:
            problems.append("%s list: %s" % (authority, error))
            print("%s: could not sync (%s)" % (authority, error))
    checked = 0
    for key in store.tracked_keys():
        result = tracker.check(key)
        _print_check(result)
        checked += 1
        problems.extend("%s %s" % (key, problem) for problem in result["problems"])
    counts = tracker.send(outbox)
    print("%d sent, %d failed" % (counts["sent"], counts["failed"]))
    if counts["failed"]:
        problems.append("%d message(s) could not be delivered" % counts["failed"])
    cutoff = (datetime.now(timezone.utc) - timedelta(days=CONFIRM_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    purged = store.purge_unconfirmed(cutoff)
    if purged:
        print("%d unconfirmed sign-up request(s) deleted" % purged)

    store.set_meta("last_run_at", tracker.now())
    store.set_meta("last_run_problems", str(len(problems)))
    store.set_meta("last_run_checked", str(checked))
    admin = os.environ.get("RERA_TRACKER_ADMIN_EMAIL", "").strip()
    if problems and admin:
        digest = "The daily RERA tracker run had %d problem(s):\n\n%s\n" % (len(problems), "\n".join("- " + p for p in problems[:30]))
        try:
            send_email(admin, "RERA tracker: %d problem(s) in today's run" % len(problems), digest)
        except DeliveryError as error:
            print("could not email the problem report: %s" % error, file=sys.stderr)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = _parser().parse_args(argv)
    today = date.fromisoformat(args.today) if args.today else None
    if args.command == "serve":
        config = web.WebConfig.from_env()
        config.db_path = args.db
        if args.dev:
            config = web.dev_config(config, args.port)
        try:
            web.serve(config, args.host, args.port, print_mail=args.dev)
        except web.ConfigError as error:
            print("The website is not configured: %s" % error, file=sys.stderr)
            return 2
        return 0

    store = Store(args.db)
    fetcher = PoliteFetcher(min_delay=args.delay, max_requests=args.max_requests)
    unsubscribe_url = None
    base_url, secret = os.environ.get("RERA_TRACKER_BASE_URL", ""), os.environ.get("RERA_TRACKER_SECRET", "")
    if base_url and secret:
        unsubscribe_url = web.make_unsubscribe_url(base_url, secret)
    tracker = Tracker(store, HaryanaSource(fetcher), today=today, unsubscribe_url=unsubscribe_url)
    try:
        if args.command == "sync":
            for authority in sorted(AUTHORITIES) if args.authority == "all" else [args.authority]:
                counts = tracker.sync(authority)
                print("%s: %d projects (%d new, %d no longer listed)" % (authority, counts["total"], counts["new"], counts["dropped"]))
        elif args.command == "stats":
            numbers = tracker.stats(args.authority)
            print("As of %s (%s):" % (fmt_date(tracker.today.isoformat(), "en"), args.authority or "all authorities"))
            for label, value in numbers.items():
                print("  %-34s %d" % (label.replace("_", " "), value))
        elif args.command == "find":
            for project in store.find_projects(args.text):
                listed = project["listed"]
                print("%-22s %-40s %-34s valid to %s%s" % (
                    project["project_id"], (project["name"] or "")[:40], (project["builder"] or "")[:34],
                    listed.get("valid_upto") or "-", "  LAPSED" if listed.get("lapsed") else ""))
        elif args.command == "subscribe":
            key = _resolve(store, args.project)
            tracker.subscribe(key, args.name, args.channel, args.address, args.lang)
            print("%s will get alerts for %s by %s." % (args.name, key, args.channel))
        elif args.command == "check":
            keys = [_resolve(store, args.project)] if args.project else store.tracked_keys()
            if not keys:
                print("No tracked projects yet. Use 'subscribe' first.")
            for key in keys:
                _print_check(tracker.check(key))
        elif args.command == "send":
            counts = tracker.send(args.outbox)
            print("%d sent, %d failed" % (counts["sent"], counts["failed"]))
        elif args.command == "report":
            print(tracker.status(_resolve(store, args.project), args.lang, args.refresh))
        elif args.command == "run":
            return _daily_run(store, tracker, args.outbox)
    except (FetchError, ParseError, KeyError, ValueError) as error:
        print("error: %s" % error, file=sys.stderr)
        return 1
    finally:
        store.close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
