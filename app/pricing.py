"""Calendar-aware pricing at hourly resolution.

Each hour of a stay is priced individually:
  1. the newest matching price rule (date range + weekdays + hours of day), else
  2. the weekend hourly rate on Friday/Saturday if set, else
  3. the listing's base hourly rate.
Then, if a daily rate exists, every full 24h block from check-in is capped at the daily rate that
applies at the block's start (rule's daily rate, else the listing's), and a partial trailing block is
capped at the same daily rate. Stays of 7+ days get the long-stay discount.

Guest pays subtotal + cleaning fee + 12% service fee. Host receives subtotal + cleaning fee - 3%.
"""
from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

from .db import rows

from . import settings

GUEST_FEE_RATE = settings.GUEST_FEE_PCT / 100
HOST_FEE_RATE = settings.HOST_FEE_PCT / 100
LONG_STAY_HOURS = 24 * 7
FMT = "%Y-%m-%dT%H:%M"


@dataclass(frozen=True)
class Quote:
    hours: float
    subtotal_cents: int
    cleaning_fee_cents: int
    service_fee_cents: int
    total_cents: int
    host_payout_cents: int
    discount_cents: int = 0
    lines: list = field(default_factory=list)   # [{"label": str, "amount_cents": int}] shown to the guest
    extra_guest_cents: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def _rule_matches(rule: dict, t: datetime) -> bool:
    d = t.strftime("%Y-%m-%d")
    return (rule["start_date"] <= d <= rule["end_date"] and str(t.weekday()) in rule["weekdays"]
            and rule["hour_from"] <= t.hour < rule["hour_until"])


def rules_for(conn: sqlite3.Connection, listing_id: int, start: datetime, end: datetime) -> list[dict]:
    return rows(conn, "SELECT * FROM price_rules WHERE listing_id = ? AND start_date <= ? AND end_date >= ? ORDER BY created_at DESC, id DESC",
                (listing_id, end.strftime("%Y-%m-%d"), start.strftime("%Y-%m-%d")))


def hour_rate(listing: dict, rules: list[dict], t: datetime) -> tuple[int, int]:
    """(hourly_rate, daily_rate) applying at hour t."""
    for r in rules:
        if _rule_matches(r, t):
            return r["hourly_rate_cents"], r["daily_rate_cents"] or listing["daily_rate_cents"]
    if t.weekday() in (4, 5) and listing.get("weekend_hourly_rate_cents"):
        return listing["weekend_hourly_rate_cents"], listing["daily_rate_cents"]
    return listing["hourly_rate_cents"], listing["daily_rate_cents"]


def day_rate(listing: dict, rules: list[dict], day: datetime) -> int:
    """Representative hourly rate for a calendar day (its noon hour), for calendar displays."""
    return hour_rate(listing, rules, day.replace(hour=12, minute=0))[0]


def stay_subtotal(listing: dict, rules: list[dict], start: datetime, end: datetime) -> tuple[int, list[dict]]:
    """Price the stay hour by hour with daily caps. Returns (subtotal_cents, lines)."""
    lines: list[dict] = []
    subtotal = 0
    t = start
    block_no = 0
    while t < end:
        block_end = min(t + timedelta(hours=24), end)
        hours_in_block = int((block_end - t).total_seconds() // 3600)
        hourly_sum = 0
        for h in range(hours_in_block):
            hourly_sum += hour_rate(listing, rules, t + timedelta(hours=h))[0]
        daily = hour_rate(listing, rules, t)[1]
        cost = min(hourly_sum, daily) if daily else hourly_sum
        subtotal += cost
        block_no += 1
        if cost == daily and daily:
            lines.append({"label": "day", "n": 1, "amount_cents": cost})
        else:
            lines.append({"label": "hours", "n": hours_in_block, "amount_cents": cost})
        t = block_end
    # Collapse consecutive identical-kind lines for display.
    merged: list[dict] = []
    for ln in lines:
        if merged and merged[-1]["label"] == ln["label"]:
            merged[-1]["n"] += ln["n"]
            merged[-1]["amount_cents"] += ln["amount_cents"]
        else:
            merged.append(dict(ln))
    return subtotal, merged


MONTH_HOURS = 24 * 30


def quote_stay(conn: sqlite3.Connection, listing: dict, start_at: str, end_at: str, guests: int = 1) -> Quote:
    start, end = datetime.strptime(start_at, FMT), datetime.strptime(end_at, FMT)
    hours = (end - start).total_seconds() / 3600
    rules = rules_for(conn, listing["id"], start, end)
    subtotal, lines = stay_subtotal(listing, rules, start, end)
    # Monthly cap: full 30-day blocks at the monthly rate when that is cheaper than the hourly/daily pricing.
    monthly = listing.get("monthly_rate_cents") or 0
    if monthly and hours >= MONTH_HOURS:
        months = int(hours // MONTH_HOURS)
        rem_start = start + timedelta(hours=months * MONTH_HOURS)
        rem_cost, rem_lines = stay_subtotal(listing, rules, rem_start, end) if rem_start < end else (0, [])
        capped = months * monthly + min(rem_cost, monthly)
        if capped < subtotal:
            subtotal = capped
            lines = [{"label": "month", "n": months, "amount_cents": months * monthly}] + ([{"label": "month", "n": 1, "amount_cents": monthly}] if rem_cost > monthly else rem_lines)
    discount = 0
    if hours >= LONG_STAY_HOURS and listing.get("long_stay_discount_pct"):
        discount = round(subtotal * listing["long_stay_discount_pct"] / 100)
        subtotal -= discount
    # Extra guests beyond the included count: per day (or per stay when under 24h).
    extra = 0
    included = listing.get("included_guests") or 0
    fee = listing.get("extra_guest_fee_cents") or 0
    if included and fee and guests > included:
        blocks = max(1, -(-int(hours) // 24))
        extra = (guests - included) * fee * blocks
    return finalize(hours, subtotal, listing["cleaning_fee_cents"], discount, lines, extra)


def finalize(hours: float, subtotal: int, cleaning_fee_cents: int, discount: int = 0, lines: list | None = None, extra_guest_cents: int = 0) -> Quote:
    base = subtotal + extra_guest_cents
    service_fee = round(base * settings.GUEST_FEE_PCT / 100)
    host_fee = round(base * settings.HOST_FEE_PCT / 100)
    return Quote(hours=hours, subtotal_cents=subtotal, cleaning_fee_cents=cleaning_fee_cents, service_fee_cents=service_fee,
                 total_cents=base + cleaning_fee_cents + service_fee, host_payout_cents=base + cleaning_fee_cents - host_fee,
                 discount_cents=discount, lines=lines or [], extra_guest_cents=extra_guest_cents)


def quote(hours: float, hourly_rate_cents: int, cleaning_fee_cents: int = 0, daily_rate_cents: int = 0) -> Quote:
    """Flat quote without calendar rules (used by tests and quick estimates)."""
    if hours <= 0:
        raise ValueError("hours must be positive")
    listing = {"hourly_rate_cents": hourly_rate_cents, "daily_rate_cents": daily_rate_cents, "weekend_hourly_rate_cents": 0}
    start = datetime(2030, 1, 7, 0, 0)  # a Monday, so weekend pricing never applies
    subtotal, lines = stay_subtotal(listing, [], start, start + timedelta(hours=hours))
    return finalize(hours, subtotal, cleaning_fee_cents, 0, lines)


# ---- cancellation policies: refund fraction of the total given hours before check-in
POLICIES = {
    "flexible": [(24, 1.0)],                       # full refund until 24h before, nothing after
    "two_days": [(48, 1.0), (24, 0.5)],            # full refund until 2 days before, half until 1 day before
    "moderate": [(5 * 24, 1.0), (24, 0.5)],        # full until 5 days, half until 24h
    "strict":   [(14 * 24, 1.0), (7 * 24, 0.5)],   # full until 14 days, half until 7 days
}


def refund_fraction(policy: str, hours_before: float) -> float:
    for threshold, fraction in POLICIES.get(policy, POLICIES["flexible"]):
        if hours_before >= threshold:
            return fraction
    return 0.0


def money(cents: int, currency: str = "$") -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    whole, frac = cents // 100, cents % 100
    return f"{sign}{currency}{whole:,}" + (f".{frac:02d}" if frac else "")
