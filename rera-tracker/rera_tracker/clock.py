"""Dates the way people in India see them.

A server usually runs on UTC.  Between midnight and 05:30 India time, the UTC
date is still yesterday, which would make "days left" and "report overdue"
off by one for a few hours every night.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

IST = timezone(timedelta(hours=5, minutes=30))


def today_ist(now: Optional[datetime] = None) -> date:
    """Today's date in India.  ``now`` must be timezone-aware if given."""
    now = now or datetime.now(timezone.utc)
    return now.astimezone(IST).date()


def utc_stamp(epoch_seconds: float) -> str:
    """The ISO UTC timestamp format used in the database."""
    return datetime.fromtimestamp(epoch_seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
