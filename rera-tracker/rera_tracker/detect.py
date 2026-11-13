"""Compare two snapshots of a project and list what a buyer should be told.

Everything here is a pure function of (old state, new state, today's date), so
it can be tested without touching the network or the database.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple

_QUARTER_END = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
_QUARTER_START_MONTH = {1: 1, 2: 4, 3: 7, 4: 10}
MAX_HEARING_EVENTS = 5


@dataclass
class Event:
    kind: str
    key: str
    data: Dict[str, object] = field(default_factory=dict)
    silent: bool = False


def quarter_end(no: int, year: int) -> date:
    month, day = _QUARTER_END[no]
    return date(year, month, day)


def quarter_start(no: int, year: int) -> date:
    return date(year, _QUARTER_START_MONTH[no], 1)


def last_ended_quarter(today: date) -> Tuple[int, int]:
    """(quarter number, year) of the latest quarter that ended before ``today``."""
    current = (today.month - 1) // 3 + 1
    if current == 1:
        return 4, today.year - 1
    return current - 1, today.year


def latest_quarter(state: Optional[dict]) -> Optional[dict]:
    quarters = (state or {}).get("quarters") or []
    if not quarters:
        return None
    return max(quarters, key=lambda q: (q["year"], q["no"]))


def hearing_id(hearing: dict) -> str:
    raw = "%s|%s|%s" % (hearing.get("date"), hearing.get("status"), hearing.get("text"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def diff_states(
    old: Optional[dict],
    new: dict,
    today: date,
    overdue_grace_days: int = 30,
    expiry_thresholds: Sequence[int] = (90, 30),
) -> List[Event]:
    """Events for the move from ``old`` to ``new``.

    The first time a project is seen (``old`` is ``None``) the only message sent
    is a "baseline" status report.  Date-driven warnings that are already true
    on that day are still returned, marked ``silent``, so that they are
    remembered and not announced again as if they were news.
    """
    first = old is None
    old = old or {}
    events: List[Event] = []

    def add(kind: str, key: str, **data: object) -> None:
        events.append(Event(kind, key, data, silent=first))

    if first:
        events.append(Event("baseline", "baseline"))
    else:
        if old.get("listed", True) and not new.get("listed", True):
            add("removed_from_list", "removed")
        for flag, kind in (
            ("lapsed", "marked_lapsed"),
            ("occ", "occ_uploaded"),
            ("corrigendum", "corrigendum_added"),
            ("monitoring", "monitoring_started"),
        ):
            if new.get(flag) and not old.get(flag):
                add(kind, flag)

        old_valid, new_valid = old.get("valid_upto"), new.get("valid_upto")
        if old_valid and new_valid and old_valid != new_valid:
            kind = "validity_extended" if new_valid > old_valid else "validity_changed"
            add(kind, "validity:%s" % new_valid, old=old_valid, new=new_valid)

        # The project page and the quarterly list are read separately.  If one of
        # them could not be read on an earlier run, what it shows now is first
        # knowledge, not a change, so it is not announced as news.
        if "hearings" in old:
            old_status, new_status = old.get("status"), new.get("status")
            if old_status and new_status and old_status != new_status:
                add("status_changed", "status:%s" % new_status, old=old_status, new=new_status)

            next_hearing = new.get("next_hearing")
            if (
                next_hearing
                and next_hearing != old.get("next_hearing")
                and next_hearing.strip().upper() not in ("NOT REQUIRED", "NA", "-", "--")
            ):
                add("next_hearing", "nexthearing:%s" % next_hearing, value=next_hearing)

            known = {hearing_id(h) for h in old.get("hearings") or []}
            fresh = [h for h in new.get("hearings") or [] if hearing_id(h) not in known]
            fresh.sort(key=lambda h: h.get("date") or "", reverse=True)
            for hearing in fresh[:MAX_HEARING_EVENTS]:
                add("new_hearing", "hearing:%s" % hearing_id(hearing), **hearing)

        new_latest, old_latest = latest_quarter(new), latest_quarter(old)
        if "quarters" in old and new_latest and (
            old_latest is None
            or (new_latest["year"], new_latest["no"]) > (old_latest["year"], old_latest["no"])
        ):
            add(
                "new_report",
                "report:%dQ%d" % (new_latest["year"], new_latest["no"]),
                quarter=new_latest,
                report=new.get("latest_report"),
                previous=old.get("latest_report"),
            )

    # Date-driven warnings: checked on every run, announced once each.
    valid_upto = new.get("valid_upto")
    if valid_upto and not new.get("occ"):
        days_left = (date.fromisoformat(valid_upto) - today).days
        if days_left < 0:
            add("registration_expired", "expired:%s" % valid_upto, valid_upto=valid_upto, days=-days_left)
        else:
            for threshold in sorted(expiry_thresholds):
                if days_left <= threshold:
                    add(
                        "registration_expiring",
                        "expiring:%d:%s" % (threshold, valid_upto),
                        valid_upto=valid_upto,
                        days=days_left,
                    )
                    break

    if "quarters" in new and not new.get("occ"):
        number, year = last_ended_quarter(today)
        end = quarter_end(number, year)
        if (today - end).days > overdue_grace_days:
            latest = latest_quarter(new)
            if latest is not None:
                missing = (latest["year"], latest["no"]) < (year, number)
            else:
                registered_on = new.get("registered_on")
                missing = bool(registered_on) and date.fromisoformat(registered_on) < quarter_start(number, year)
            if missing:
                add(
                    "report_overdue",
                    "overdue:%dQ%d" % (year, number),
                    quarter_no=number,
                    quarter_year=year,
                    quarter_end=end.isoformat(),
                    latest=latest,
                )
    return events
