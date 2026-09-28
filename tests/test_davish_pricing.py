"""Pricing behaviours needed for Davish's House price list."""
from app.db import row
from app.pricing import quote_stay, refund_fraction


def listing(conn, **over):
    l = dict(row(conn, "SELECT * FROM listings WHERE id = 1"))
    l.update(over)
    return l


def test_four_hour_block_then_daily_cap(conn):
    l = listing(conn, hourly_rate_cents=16250, daily_rate_cents=95000, monthly_rate_cents=1700000, min_hours=4)   # depa 51
    assert quote_stay(conn, l, "2026-10-05T10:00", "2026-10-05T14:00").subtotal_cents == 65000       # 4h = $650
    assert quote_stay(conn, l, "2026-10-05T10:00", "2026-10-05T15:00").subtotal_cents == 81250       # 5h hourly
    assert quote_stay(conn, l, "2026-10-05T10:00", "2026-10-05T20:00").subtotal_cents == 95000       # 10h capped at day
    assert quote_stay(conn, l, "2026-10-05T10:00", "2026-10-07T10:00").subtotal_cents == 190000      # 2 days


def test_monthly_cap(conn):
    l = listing(conn, hourly_rate_cents=16250, daily_rate_cents=95000, monthly_rate_cents=1700000, min_hours=4)
    q = quote_stay(conn, l, "2026-10-05T10:00", "2026-11-04T10:00")   # exactly 30 days
    assert q.subtotal_cents == 1700000 and q.lines[0]["label"] == "month"
    q = quote_stay(conn, l, "2026-10-05T10:00", "2026-11-06T10:00")   # 30 days + 2 days
    assert q.subtotal_cents == 1700000 + 2 * 95000
    q = quote_stay(conn, l, "2026-10-05T10:00", "2026-12-04T10:00")   # 60 days
    assert q.subtotal_cents == 2 * 1700000


def test_extra_guest_fee(conn):
    l = listing(conn, hourly_rate_cents=16250, daily_rate_cents=95000, included_guests=2, extra_guest_fee_cents=10000, capacity=4, cleaning_fee_cents=0)
    assert quote_stay(conn, l, "2026-10-05T10:00", "2026-10-05T14:00", guests=2).extra_guest_cents == 0
    q = quote_stay(conn, l, "2026-10-05T10:00", "2026-10-05T14:00", guests=3)
    assert q.extra_guest_cents == 10000 and q.total_cents == 65000 + 10000 + round(75000 * .12)
    assert quote_stay(conn, l, "2026-10-05T10:00", "2026-10-08T10:00", guests=4).extra_guest_cents == 2 * 3 * 10000


def test_two_day_policy():
    assert refund_fraction("two_days", 49) == 1.0 and refund_fraction("two_days", 30) == 0.5 and refund_fraction("two_days", 12) == 0.0


def test_beach_apartment_daily_only(conn):
    l = listing(conn, hourly_rate_cents=round(2500 / 24 * 100), daily_rate_cents=250000, min_hours=24)
    assert quote_stay(conn, l, "2026-10-05T10:00", "2026-10-06T10:00").subtotal_cents == 250000
    assert quote_stay(conn, l, "2026-10-05T10:00", "2026-10-08T10:00").subtotal_cents == 750000
