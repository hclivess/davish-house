from datetime import date, datetime

import pytest

from app.availability import AvailabilityError, busy_ranges, check_range, free_hours_by_day
from app.bookings import BookingError, cancel, create_booking, host_respond
from app.db import row
from app.pricing import quote, quote_stay, refund_fraction

NOW = datetime(2026, 10, 1, 8, 0)
D1, D2, D3 = "2026-10-02", "2026-10-03", "2026-10-04"


def listing(conn, lid=1):
    return row(conn, "SELECT * FROM listings WHERE id = ?", (lid,))


def test_quote_math():
    q = quote(3, 5000, 1000)
    assert q.subtotal_cents == 15000 and q.service_fee_cents == 1800 and q.total_cents == 17800
    assert q.host_payout_cents == 15000 + 1000 - 450


def test_daily_rate_caps_full_days():
    q = quote(30, 1000, 0, daily_rate_cents=15000)   # 30h: one day capped at 150 + 6h at 10 = 210
    assert q.subtotal_cents == 21000
    assert [(l["label"], l["n"]) for l in q.lines] == [("day", 1), ("hours", 6)]
    q = quote(47, 1000, 0, daily_rate_cents=15000)   # 47h: day + 23h (230 > 150) -> two days
    assert q.subtotal_cents == 30000


def test_multi_day_stay_allowed(conn):
    b = create_booking(conn, 1, 2, f"{D1}T15:00", f"{D3}T11:00", now=NOW)   # 44 hours across three calendar days
    assert b["status"] == "confirmed" and b["hours"] == 44 and b["subtotal_cents"] == 44 * 5000


def test_buffer_blocks_neighbouring_hours(conn):
    create_booking(conn, 1, 2, f"{D1}T12:00", f"{D1}T14:00", now=NOW)
    with pytest.raises(BookingError, match="no longer available"):
        create_booking(conn, 1, 3, f"{D1}T14:00", f"{D1}T15:00", now=NOW)   # inside the 60-min buffer
    with pytest.raises(BookingError, match="no longer available"):
        create_booking(conn, 1, 3, f"{D1}T10:00", f"{D1}T12:00", now=NOW)   # ends when buffer-padded booking starts (11:00)
    assert create_booking(conn, 1, 3, f"{D1}T15:00", f"{D1}T17:00", now=NOW)["status"] == "confirmed"
    busy = busy_ranges(conn, listing(conn), date(2026, 10, 2), 1, NOW)
    assert busy == [{"start": f"{D1}T11:00", "end": f"{D1}T18:00"}]
    assert free_hours_by_day(busy, date(2026, 10, 2), 1)[0] == {"date": D1, "free_hours": 17, "state": "partial", }


@pytest.mark.parametrize("lid,start,end,msg", [
    (1, f"{D1}T10:30", f"{D1}T12:00", "on the hour"),
    (1, "2026-09-30T10:00", "2026-09-30T12:00", "in the past"),
    (1, f"{D1}T12:00", f"{D1}T11:00", "after check-in"),
    (2, f"{D1}T10:00", f"{D1}T11:00", "Minimum stay"),
    (2, f"{D1}T20:00", f"{D1}T23:00", "Check-in is only possible"),
    (1, f"{D1}T10:00", "2027-01-01T10:00", "Maximum stay"),
])
def test_check_range_rules(conn, lid, start, end, msg):
    with pytest.raises(AvailabilityError, match=msg):
        check_range(conn, listing(conn, lid), start, end, now=NOW)


def test_advance_notice_and_window(conn):
    conn.execute("UPDATE listings SET advance_notice_hours = 12, max_advance_days = 10 WHERE id = 1")
    with pytest.raises(AvailabilityError, match="notice"):
        check_range(conn, listing(conn), "2026-10-01T15:00", "2026-10-01T17:00", now=NOW)
    with pytest.raises(AvailabilityError, match="in advance"):
        check_range(conn, listing(conn), "2026-10-20T15:00", "2026-10-20T17:00", now=NOW)
    assert check_range(conn, listing(conn), "2026-10-05T15:00", "2026-10-05T17:00", now=NOW) == 2


def test_host_block_removes_availability(conn):
    conn.execute("INSERT INTO availability_blocks (listing_id, start_at, end_at) VALUES (1, ?, ?)", (f"{D1}T09:00", f"{D1}T12:00"))
    with pytest.raises(BookingError):
        create_booking(conn, 1, 2, f"{D1}T10:00", f"{D1}T11:00", now=NOW)
    assert create_booking(conn, 1, 2, f"{D1}T12:00", f"{D1}T13:00", now=NOW)["status"] == "confirmed"


def test_price_rules_apply_per_hour(conn):
    # Nights (22-06) cost 20/h on Oct 2-3; everything else base 50/h.
    conn.execute("""INSERT INTO price_rules (listing_id, start_date, end_date, hour_from, hour_until, hourly_rate_cents) VALUES (1, ?, ?, 22, 24, 2000)""", (D1, D2))
    conn.execute("""INSERT INTO price_rules (listing_id, start_date, end_date, hour_from, hour_until, hourly_rate_cents) VALUES (1, ?, ?, 0, 6, 2000)""", (D1, D2))
    q = quote_stay(conn, listing(conn), f"{D1}T20:00", f"{D2}T08:00")   # 2h@50 + 8h@20 + 2h@50 = 100+160+100
    assert q.subtotal_cents == 36000
    # Weekday-limited rule: only Saturdays (weekday 5). Oct 3 2026 is a Saturday.
    conn.execute("""INSERT INTO price_rules (listing_id, start_date, end_date, weekdays, hourly_rate_cents) VALUES (1, ?, ?, '5', 9000)""", (D1, D3))
    assert quote_stay(conn, listing(conn), f"{D2}T10:00", f"{D2}T12:00").subtotal_cents == 18000
    assert quote_stay(conn, listing(conn), f"{D1}T10:00", f"{D1}T12:00").subtotal_cents == 10000


def test_weekend_rate_and_long_stay_discount(conn):
    conn.execute("UPDATE listings SET weekend_hourly_rate_cents = 7000, long_stay_discount_pct = 10 WHERE id = 1")
    assert quote_stay(conn, listing(conn), f"{D1}T10:00", f"{D1}T12:00").subtotal_cents == 14000   # Friday
    q = quote_stay(conn, listing(conn), "2026-10-05T10:00", "2026-10-12T10:00")   # 7 days Mon-Mon: 120h @50 + 48h Fri/Sat @70 = 9360, -10%
    assert q.discount_cents == 93600 and q.subtotal_cents == 842400


def test_request_to_book_flow(conn):
    b = create_booking(conn, 2, 2, f"{D1}T10:00", f"{D1}T12:00", now=NOW)
    assert b["status"] == "pending" and b["payment_status"] == "authorized"
    with pytest.raises(BookingError):
        host_respond(conn, b["id"], host_id=2, accept=True)
    b = host_respond(conn, b["id"], host_id=1, accept=True)
    assert b["status"] == "confirmed" and b["payment_status"] == "paid"


def test_cancellation_policies():
    assert refund_fraction("flexible", 30) == 1.0 and refund_fraction("flexible", 10) == 0.0
    assert refund_fraction("moderate", 24 * 6) == 1.0 and refund_fraction("moderate", 48) == 0.5 and refund_fraction("moderate", 5) == 0.0
    assert refund_fraction("strict", 24 * 15) == 1.0 and refund_fraction("strict", 24 * 8) == 0.5 and refund_fraction("strict", 24 * 6) == 0.0


def test_cancel_applies_policy(conn):
    conn.execute("UPDATE listings SET cancellation_policy = 'moderate' WHERE id = 1")
    b = create_booking(conn, 1, 2, "2026-10-03T10:00", "2026-10-03T12:00", now=NOW)   # 50h ahead -> 50%
    b = cancel(conn, b["id"], 2, now=NOW)
    assert b["status"] == "cancelled" and b["refund_cents"] == round(b["total_cents"] * 0.5) and b["payment_status"] == "refunded"
    b2 = create_booking(conn, 1, 2, "2026-10-03T10:00", "2026-10-03T12:00", now=NOW)   # slot free again
    b2 = cancel(conn, b2["id"], 1, now=NOW)   # host cancels: full refund
    assert b2["refund_cents"] == b2["total_cents"]


def test_capacity_and_self_booking(conn):
    with pytest.raises(BookingError, match="holds up to"):
        create_booking(conn, 1, 2, f"{D1}T10:00", f"{D1}T12:00", guests=9, now=NOW)
    with pytest.raises(BookingError, match="own listing"):
        create_booking(conn, 1, 1, f"{D1}T10:00", f"{D1}T12:00", now=NOW)
