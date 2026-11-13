"""Ties the pieces together: sync the list, check tracked projects, queue messages."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Callable, Dict, List, Optional

from .detect import Event, diff_states
from .fetch import FetchError
from .haryana import AUTHORITIES, HaryanaSource, ParseError
from .messages import render, render_status
from .notify import DeliveryError, deliver
from .store import Store

_LISTED_FIELDS = (
    "authority", "project_id", "name", "builder", "location", "district", "reg_no", "registered_on",
    "valid_upto", "lapsed", "corrigendum", "occ", "monitoring", "detail_url",
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_state(
    listed: dict,
    in_list: bool,
    detail: Optional[dict],
    quarters: Optional[List[dict]],
    report: Optional[dict],
    previous: Optional[dict],
) -> dict:
    """Merge what was read today into one snapshot.

    Parts that could not be read today (``None``) are carried over from the
    previous snapshot, so a failed request never looks like a change.
    """
    previous = previous or {}
    state: Dict[str, object] = {field: listed.get(field) for field in _LISTED_FIELDS}
    state["listed"] = bool(in_list)
    state["list_url"] = HaryanaSource.list_url(str(listed["authority"]))
    if detail is not None:
        state["status"] = detail.get("status")
        state["next_hearing"] = detail.get("next_hearing")
        state["hearings"] = detail.get("hearings") or []
    else:
        for field in ("status", "next_hearing", "hearings"):
            if field in previous:
                state[field] = previous[field]
    if quarters is not None:
        state["quarters"] = quarters
        state["latest_report"] = report
    else:
        for field in ("quarters", "latest_report"):
            if field in previous:
                state[field] = previous[field]
    return state


class Tracker:
    def __init__(
        self,
        store: Store,
        source: HaryanaSource,
        today: Optional[date] = None,
        now: Callable[[], str] = _now,
        overdue_grace_days: int = 30,
    ) -> None:
        self.store = store
        self.source = source
        self.today = today or date.today()
        self.now = now
        self.overdue_grace_days = overdue_grace_days

    # -- list ----------------------------------------------------------------
    def sync(self, authority: str) -> Dict[str, int]:
        if authority not in AUTHORITIES:
            raise ValueError("unknown authority %r (choose from %s)" % (authority, ", ".join(sorted(AUTHORITIES))))
        listed = [p.to_dict() for p in self.source.fetch_listed(authority)]
        if not listed:
            raise ParseError("the %s list came back empty; keeping the stored list" % authority)
        counts = self.store.upsert_listed(authority, listed, self.now())
        self.store.set_meta("synced:%s" % authority, self.now())
        return counts

    # -- one project ---------------------------------------------------------
    def check(self, key: str) -> Dict[str, object]:
        """Read one project's pages, record what changed and queue messages."""
        project = self.store.get_project(key)
        if project is None:
            raise KeyError("unknown project %r; run sync first" % key)
        listed, old = project["listed"], project["state"]
        problems: List[str] = []

        detail = None
        if listed.get("detail_url"):
            try:
                detail = self.source.fetch_detail(listed["detail_url"]).to_dict()
            except (FetchError, ParseError, ValueError) as error:
                problems.append("details page: %s" % error)

        quarters = report = None
        if listed.get("qpr_url"):
            try:
                found = self.source.fetch_quarters(listed["qpr_url"])
                quarters = [q.to_dict() for q in found]
                if found:
                    latest = found[-1]
                    marker = [latest.year, latest.no]
                    old_report = (old or {}).get("latest_report")
                    if old_report and old_report.get("quarter") == marker:
                        report = old_report
                    elif latest.action:
                        report = dict(self.source.fetch_report(latest).to_dict(), quarter=marker)
            except (FetchError, ParseError, ValueError) as error:
                # Try again on the next run rather than announce a report without its figures.
                problems.append("quarterly reports: %s" % error)
                quarters = report = None

        state = build_state(listed, project["in_list"], detail, quarters, report, old)
        events = diff_states(old, state, self.today, overdue_grace_days=self.overdue_grace_days)
        stamp = self.now()
        self.store.save_state(key, state, stamp)
        queued = 0
        fresh: List[Event] = []
        for event in events:
            event_id = self.store.record_event(key, event.kind, event.key, event.data, stamp, event.silent)
            if event_id is None:
                continue
            fresh.append(event)
            if event.silent:
                continue
            for subscriber in self.store.subscribers_for(key):
                subject, body = render(event, state, self.today, subscriber["lang"])
                queued += int(self.store.queue_message(subscriber["id"], event_id, subject, body, stamp))
        return {"key": key, "events": fresh, "queued": queued, "problems": problems, "state": state}

    def check_all(self) -> List[Dict[str, object]]:
        return [self.check(key) for key in self.store.tracked_keys()]

    # -- subscribers ---------------------------------------------------------
    def subscribe(self, key: str, name: str, channel: str, address: str, lang: str = "en") -> int:
        project = self.store.get_project(key)
        if project is None:
            raise KeyError("unknown project %r; run sync first" % key)
        stamp = self.now()
        subscriber_id = self.store.add_subscriber(name, channel, address, lang, stamp)
        self.store.subscribe(subscriber_id, key, stamp)
        # A project that is already tracked has its first report on file: send it to the newcomer.
        baseline = self.store.find_event(key, "baseline")
        if baseline is not None and project["state"]:
            event = Event("baseline", "baseline")
            subject, body = render(event, project["state"], self.today, lang)
            self.store.queue_message(subscriber_id, baseline, subject, body, stamp)
        return subscriber_id

    # -- output --------------------------------------------------------------
    def status(self, key: str, lang: str = "en", refresh: bool = False) -> str:
        project = self.store.get_project(key)
        if project is None:
            raise KeyError("unknown project %r; run sync first" % key)
        state = project["state"]
        if refresh or not state:
            state = self.check(key)["state"]
        return render_status(state, self.today, lang, self.overdue_grace_days)

    def send(self, outbox_dir: str = "outbox", out: Optional[Callable[[str], None]] = None) -> Dict[str, int]:
        sent = failed = 0
        for message in self.store.pending_messages():
            try:
                deliver(message["channel"], message["address"], message["subject"], message["body"],
                        message_id=message["id"], outbox_dir=outbox_dir, out=out)
            except DeliveryError as error:
                failed += 1
                self.store.mark_sent(message["id"], None, str(error))
            else:
                sent += 1
                self.store.mark_sent(message["id"], self.now())
        return {"sent": sent, "failed": failed}

    # -- numbers -------------------------------------------------------------
    def stats(self, authority: Optional[str] = None) -> Dict[str, int]:
        listed = self.store.all_listed(authority)
        today = self.today.isoformat()
        soon = self.today.toordinal() + 180
        passed = [p for p in listed if p.get("valid_upto") and p["valid_upto"] < today]
        return {
            "projects": len(listed),
            "lapsed": sum(1 for p in listed if p.get("lapsed")),
            "with_occ": sum(1 for p in listed if p.get("occ")),
            "validity_passed": len(passed),
            "validity_passed_without_occ": sum(1 for p in passed if not p.get("occ")),
            "validity_ends_within_180_days": sum(
                1 for p in listed
                if p.get("valid_upto") and today <= p["valid_upto"] and date.fromisoformat(p["valid_upto"]).toordinal() <= soon
            ),
            "with_quarterly_reports": sum(1 for p in listed if p.get("qpr_url")),
        }
