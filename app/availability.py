"""Availability engine: hourly resolution, any length of stay.

An apartment is available continuously except where a booking (padded by the cleaning buffer)
or a host block sits. A stay is a [check_in, check_out) interval on whole-hour boundaries and may
span any number of days. Hosts can optionally restrict the hours of day at which guests may
check in and check out (e.g. check-in 08:00–22:00), which applies on every day.

All times are naive local ISO strings: "YYYY-MM-DDTHH:MM" in the listing's timezone.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .db import rows
from .i18n import _
from .timezones import local_now

SLOT_MINUTES = 60  # booking resolution
ACTIVE_BOOKING_STATUSES = ("awaiting_payment", "pending", "confirmed")
FMT = "%Y-%m-%dT%H:%M"


def parse_dt(s: str) -> datetime:
    return datetime.strptime(s, FMT)


def fmt_dt(d: datetime) -> str:
    return d.strftime(FMT)


def _hhmm_minutes(hhmm: str) -> int:
    h, m = (int(x) for x in hhmm.split(":"))
    return h * 60 + m


@dataclass(frozen=True)
class Interval:
    start: datetime
    end: datetime

    def overlaps(self, other: "Interval") -> bool:
        return self.start < other.end and other.start < self.end


def occupied_intervals(
    conn: sqlite3.Connection, listing_id: int, lo: datetime, hi: datetime, buffer_minutes: int,
    exclude_booking_id: int | None = None,
) -> list[Interval]:
    """Bookings (padded by the buffer) and blocks that touch [lo, hi)."""
    pad = timedelta(minutes=buffer_minutes)
    placeholders = ",".join("?" * len(ACTIVE_BOOKING_STATUSES))
    sql = (
        f"SELECT id, start_at, end_at FROM bookings WHERE listing_id = ? AND status IN ({placeholders}) "
        "AND start_at < ? AND end_at > ?"
    )
    params: list = [listing_id, *ACTIVE_BOOKING_STATUSES, fmt_dt(hi + pad), fmt_dt(lo - pad)]
    if exclude_booking_id is not None:
        sql += " AND id != ?"
        params.append(exclude_booking_id)
    out = [Interval(parse_dt(b["start_at"]) - pad, parse_dt(b["end_at"]) + pad) for b in rows(conn, sql, params)]
    blocks = rows(
        conn,
        "SELECT start_at, end_at FROM availability_blocks WHERE listing_id = ? AND start_at < ? AND end_at > ?",
        (listing_id, fmt_dt(hi), fmt_dt(lo)),
    )
    out += [Interval(parse_dt(b["start_at"]), parse_dt(b["end_at"])) for b in blocks]
    out.sort(key=lambda i: i.start)
    return out


def merge(intervals: list[Interval]) -> list[Interval]:
    merged: list[Interval] = []
    for iv in sorted(intervals, key=lambda i: i.start):
        if merged and iv.start <= merged[-1].end:
            merged[-1] = Interval(merged[-1].start, max(merged[-1].end, iv.end))
        else:
            merged.append(iv)
    return merged


def busy_ranges(conn: sqlite3.Connection, listing: dict, from_day: date, days: int, now: datetime | None = None) -> list[dict]:
    """Merged unavailable ranges (bookings + buffers + blocks + the past) clipped to the window, for calendars."""
    now = now or local_now(listing.get("timezone"))
    lo = datetime.combine(from_day, datetime.min.time())
    hi = lo + timedelta(days=days)
    busy = occupied_intervals(conn, listing["id"], lo, hi, listing["buffer_minutes"])
    if now > lo:
        busy.append(Interval(lo, min(now, hi)))
    out = []
    for iv in merge(busy):
        s, e = max(iv.start, lo), min(iv.end, hi)
        if s < e:
            out.append({"start": fmt_dt(s), "end": fmt_dt(e)})
    return out


def free_hours_by_day(busy: list[dict], from_day: date, days: int) -> list[dict]:
    """Per-day summary for a calendar strip: hours free out of 24."""
    out = []
    for i in range(days):
        d = from_day + timedelta(days=i)
        d0 = datetime.combine(d, datetime.min.time())
        d1 = d0 + timedelta(days=1)
        blocked = timedelta()
        for b in busy:
            s, e = max(parse_dt(b["start"]), d0), min(parse_dt(b["end"]), d1)
            if s < e:
                blocked += e - s
        free_h = 24 - blocked.total_seconds() / 3600
        out.append({"date": d.isoformat(), "free_hours": round(free_h, 1),
                    "state": "free" if free_h >= 23.99 else ("busy" if free_h <= 0.01 else "partial")})
    return out


class AvailabilityError(ValueError):
    pass


def _in_window(t: datetime, from_hhmm: str, until_hhmm: str) -> bool:
    """Is the time-of-day of t within [from, until]? '24:00' as until means end of day. Windows may wrap midnight."""
    m = t.hour * 60 + t.minute
    lo, hi = _hhmm_minutes(from_hhmm), _hhmm_minutes(until_hhmm)
    if lo <= hi:
        return lo <= m <= hi
    return m >= lo or m <= hi


def check_range(
    conn: sqlite3.Connection, listing: dict, start_at: str, end_at: str,
    now: datetime | None = None, exclude_booking_id: int | None = None,
) -> float:
    """Validate a requested stay against every rule. Returns hours on success, raises AvailabilityError otherwise."""
    now = now or local_now(listing.get("timezone"))
    try:
        start, end = parse_dt(start_at), parse_dt(end_at)
    except ValueError:
        raise AvailabilityError(_("Times must be formatted YYYY-MM-DDTHH:MM."))
    if end <= start:
        raise AvailabilityError(_("Check-out must be after check-in."))
    if start < now:
        raise AvailabilityError(_("Check-in time is in the past."))
    notice = listing.get("advance_notice_hours") or 0
    if notice and start < now + timedelta(hours=notice):
        raise AvailabilityError(_("This host needs %s hours' notice before check-in.") % notice)
    window = listing.get("max_advance_days") or 0
    if window and start > now + timedelta(days=window):
        raise AvailabilityError(_("Bookings can be made at most %s days in advance.") % window)
    if start.minute % SLOT_MINUTES or end.minute % SLOT_MINUTES:
        raise AvailabilityError(_("Times must be on the hour."))
    hours = (end - start).total_seconds() / 3600
    if hours < listing["min_hours"]:
        raise AvailabilityError(_("Minimum stay is %s hours.") % f"{listing['min_hours']:g}")
    if hours > listing["max_hours"]:
        raise AvailabilityError(_("Maximum stay is %s hours.") % f"{listing['max_hours']:g}")
    if not _in_window(start, listing.get("checkin_from") or "00:00", listing.get("checkin_until") or "24:00"):
        raise AvailabilityError(_("Check-in is only possible between %s and %s.") % (listing["checkin_from"], listing["checkin_until"]))
    if not _in_window(end, listing.get("checkout_from") or "00:00", listing.get("checkout_until") or "24:00"):
        raise AvailabilityError(_("Check-out is only possible between %s and %s.") % (listing["checkout_from"], listing["checkout_until"]))
    requested = Interval(start, end)
    busy = occupied_intervals(conn, listing["id"], start, end, listing["buffer_minutes"], exclude_booking_id)
    if any(requested.overlaps(b) for b in busy):
        raise AvailabilityError(_("Those hours are no longer available."))
    return hours


def listing_is_free(conn: sqlite3.Connection, listing: dict, start_at: str, end_at: str, now: datetime | None = None) -> bool:
    try:
        check_range(conn, listing, start_at, end_at, now)
        return True
    except AvailabilityError:
        return False


def format_duration(hours: float, lang: str = "en") -> str:
    days, rem = divmod(int(round(hours)), 24)
    parts = []
    if days:
        parts.append(f"{days} " + (("día" if days == 1 else "días") if lang == "es" else ("day" if days == 1 else "days")))
    if rem or not days:
        parts.append(f"{rem} " + (("hora" if rem == 1 else "horas") if lang == "es" else ("hour" if rem == 1 else "hours")))
    return " ".join(parts)
