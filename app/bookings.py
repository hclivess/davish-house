"""Booking lifecycle: create (conflict-safe), pay, confirm, decline, cancel, expire, complete.

Statuses
  awaiting_payment  slot held while the guest pays on Stripe Checkout (expires after PAYMENT_WINDOW_MINUTES)
  pending           request-to-book, card authorized, waiting for the host
  confirmed         paid and scheduled
  declined | cancelled | expired | completed
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from . import notify, payments
from .availability import AvailabilityError, check_range, parse_dt
from .db import row, transaction
from .i18n import _
from .pricing import quote_stay, refund_fraction
from .timezones import local_now

ACTIVE = ("awaiting_payment", "pending", "confirmed")


class BookingError(ValueError):
    pass


def _utc_stamp(dt: datetime | None = None) -> str:
    return (dt or datetime.utcnow()).strftime("%Y-%m-%dT%H:%M")


def get_listing(conn: sqlite3.Connection, listing_id: int) -> dict | None:
    return row(conn, "SELECT * FROM listings WHERE id = ?", (listing_id,))


def get_booking(conn: sqlite3.Connection, booking_id: int) -> dict | None:
    return row(conn, "SELECT b.*, l.host_id, l.timezone FROM bookings b JOIN listings l ON l.id = b.listing_id WHERE b.id = ?", (booking_id,))


def create_booking(
    conn: sqlite3.Connection, listing_id: int, guest_id: int, start_at: str, end_at: str,
    guests: int = 1, note: str = "", now: datetime | None = None,
) -> dict:
    """Reserve the slot. With Stripe configured the booking starts as awaiting_payment; otherwise it is
    confirmed (or pending for request-to-book) immediately in simulated-payment mode."""
    with transaction(conn):
        listing = get_listing(conn, listing_id)
        if not listing or listing["status"] != "active":
            raise BookingError(_("Listing is not available for booking."))
        if listing["host_id"] == guest_id:
            raise BookingError(_("You cannot book your own listing."))
        if guests < 1 or guests > listing["capacity"]:
            raise BookingError(_("This space holds up to %s people.") % listing["capacity"])
        try:
            hours = check_range(conn, listing, start_at, end_at, now)
        except AvailabilityError as e:
            raise BookingError(str(e)) from e
        q = quote_stay(conn, listing, start_at, end_at, guests)
        if payments.configured():
            status, payment_status = "awaiting_payment", "unpaid"
            expires = _utc_stamp(datetime.utcnow() + timedelta(minutes=payments.PAYMENT_WINDOW_MINUTES))
        else:
            status = "confirmed" if listing["instant_book"] else "pending"
            payment_status = "paid" if status == "confirmed" else "authorized"
            expires = None
        cur = conn.execute(
            """INSERT INTO bookings (listing_id, guest_id, start_at, end_at, guests, hours, subtotal_cents,
               cleaning_fee_cents, service_fee_cents, total_cents, host_payout_cents, status, payment_status, note, expires_at, extra_guest_cents)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (listing_id, guest_id, start_at, end_at, guests, hours, q.subtotal_cents, q.cleaning_fee_cents,
             q.service_fee_cents, q.total_cents, q.host_payout_cents, status, payment_status, note.strip()[:1000], expires, q.extra_guest_cents),
        )
        booking_id = cur.lastrowid
    if status == "confirmed":
        notify.booking_confirmed(conn, booking_id)
    elif status == "pending":
        notify.booking_requested(conn, booking_id)
    return row(conn, "SELECT * FROM bookings WHERE id = ?", (booking_id,))


def start_checkout(conn: sqlite3.Connection, booking_id: int, guest_email: str, base_url: str) -> str:
    """Create (or reuse) a Stripe Checkout session for an awaiting_payment booking. Returns the hosted URL."""
    b = get_booking(conn, booking_id)
    if not b or b["status"] != "awaiting_payment":
        raise BookingError(_("This booking is not awaiting payment."))
    listing = get_listing(conn, b["listing_id"])
    try:
        s = payments.create_checkout_session(b, listing, guest_email, base_url)
    except payments.PaymentError as e:
        raise BookingError(_("Payment could not be started: %s") % e) from e
    conn.execute("UPDATE bookings SET stripe_session_id = ?, stripe_payment_intent = COALESCE(?, stripe_payment_intent) WHERE id = ?",
                 (s["id"], s["payment_intent"], booking_id))
    return s["url"]


def mark_paid(conn: sqlite3.Connection, booking_id: int, payment_intent: str | None) -> dict:
    """Called from the webhook / return-page sync once Checkout completed. Idempotent."""
    b = get_booking(conn, booking_id)
    if not b:
        raise BookingError(_("Booking not found."))
    if b["status"] != "awaiting_payment":
        return b
    listing = get_listing(conn, b["listing_id"])
    if listing["instant_book"]:
        status, payment_status = "confirmed", "paid"
    else:
        status, payment_status = "pending", "authorized"
    conn.execute("UPDATE bookings SET status = ?, payment_status = ?, stripe_payment_intent = COALESCE(?, stripe_payment_intent), expires_at = NULL WHERE id = ?",
                 (status, payment_status, payment_intent, booking_id))
    if status == "confirmed":
        notify.booking_confirmed(conn, booking_id)
    else:
        notify.booking_requested(conn, booking_id)
    return get_booking(conn, booking_id)


def sync_payment(conn: sqlite3.Connection, booking_id: int) -> dict:
    """If the webhook hasn't arrived yet, ask Stripe directly whether the session was paid."""
    b = get_booking(conn, booking_id)
    if not b or b["status"] != "awaiting_payment" or not b["stripe_session_id"] or not payments.configured():
        return b
    try:
        s = payments.retrieve_session(b["stripe_session_id"])
    except payments.PaymentError:
        return b
    if s["status"] == "complete" and s["payment_status"] in ("paid", "unpaid"):
        # 'unpaid' + complete happens for manual-capture (authorized) sessions.
        return mark_paid(conn, booking_id, s["payment_intent"])
    if s["status"] == "expired":
        return _set_status(conn, booking_id, "expired")
    return b


def _set_status(conn: sqlite3.Connection, booking_id: int, status: str, payment_status: str | None = None) -> dict:
    if payment_status:
        conn.execute("UPDATE bookings SET status = ?, payment_status = ? WHERE id = ?", (status, payment_status, booking_id))
    else:
        conn.execute("UPDATE bookings SET status = ? WHERE id = ?", (status, booking_id))
    return get_booking(conn, booking_id)


def host_respond(conn: sqlite3.Connection, booking_id: int, host_id: int, accept: bool) -> dict:
    b = get_booking(conn, booking_id)
    if not b or b["host_id"] != host_id:
        raise BookingError(_("Booking not found."))
    if b["status"] != "pending":
        raise BookingError(_("Only pending requests can be accepted or declined."))
    pi = b["stripe_payment_intent"]
    try:
        if accept:
            if pi and payments.configured():
                payments.capture(pi)
            out = _set_status(conn, booking_id, "confirmed", "paid")
        else:
            if pi and payments.configured():
                payments.release(pi)
            out = _set_status(conn, booking_id, "declined", "refunded")
        notify.request_answered(conn, booking_id, accept)
        return out
    except payments.PaymentError as e:
        raise BookingError(_("Stripe error: %s") % e) from e


def cancel(conn: sqlite3.Connection, booking_id: int, user_id: int, now: datetime | None = None) -> dict:
    b = get_booking(conn, booking_id)
    if not b or user_id not in (b["guest_id"], b["host_id"]):
        raise BookingError(_("Booking not found."))
    now = now or local_now(b["timezone"])
    if b["status"] not in ACTIVE:
        raise BookingError(_("This booking can no longer be cancelled."))
    if parse_dt(b["start_at"]) <= now:
        raise BookingError(_("The booking has already started."))
    if b["status"] == "awaiting_payment":
        return _set_status(conn, booking_id, "cancelled", "unpaid")
    hours_before = (parse_dt(b["start_at"]) - now).total_seconds() / 3600
    listing = get_listing(conn, b["listing_id"])
    # Host cancellations refund in full; guest cancellations follow the listing's cancellation policy.
    fraction = 1.0 if user_id == b["host_id"] or b["status"] == "pending" else refund_fraction(listing["cancellation_policy"], hours_before)
    refund_cents = round(b["total_cents"] * fraction)
    pi = b["stripe_payment_intent"]
    try:
        if pi and payments.configured():
            if b["status"] == "pending":          # only authorized: release the hold
                payments.release(pi)
            elif refund_cents:
                payments.refund(pi, None if fraction >= 1.0 else refund_cents)
    except payments.PaymentError as e:
        raise BookingError(_("Stripe error: %s") % e) from e
    conn.execute("UPDATE bookings SET refund_cents = ? WHERE id = ?", (refund_cents, booking_id))
    out = _set_status(conn, booking_id, "cancelled", "refunded" if refund_cents else "paid")
    notify.booking_cancelled(conn, booking_id, by_host=(user_id == b["host_id"]))
    return out


def expire_unpaid(conn: sqlite3.Connection, now: datetime | None = None) -> int:
    """Release slots whose payment window lapsed. Called lazily on page loads."""
    cur = conn.execute("UPDATE bookings SET status = 'expired' WHERE status = 'awaiting_payment' AND expires_at IS NOT NULL AND expires_at <= ?",
                       (_utc_stamp(now),))
    return cur.rowcount


def complete_past(conn: sqlite3.Connection, now: datetime | None = None) -> int:
    """Mark confirmed bookings whose end time has passed (in the listing's zone) as completed. Called lazily on page loads."""
    expire_unpaid(conn)
    total = 0
    for (tz,) in conn.execute("SELECT DISTINCT timezone FROM listings").fetchall():
        stamp = (now or local_now(tz)).strftime("%Y-%m-%dT%H:%M")
        cur = conn.execute(
            "UPDATE bookings SET status = 'completed' WHERE status = 'confirmed' AND end_at <= ? "
            "AND listing_id IN (SELECT id FROM listings WHERE timezone = ?)",
            (stamp, tz),
        )
        total += cur.rowcount
    return total


def handle_webhook_event(conn: sqlite3.Connection, event: dict) -> str:
    """Apply a verified Stripe event. Returns a short description for logging."""
    kind = event.get("type", "")
    obj = event.get("data", {}).get("object", {})
    if kind in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        bid = int((obj.get("metadata") or {}).get("booking_id") or obj.get("client_reference_id") or 0)
        if bid:
            mark_paid(conn, bid, obj.get("payment_intent"))
            return f"booking {bid} paid"
    elif kind in ("checkout.session.expired", "checkout.session.async_payment_failed"):
        bid = int((obj.get("metadata") or {}).get("booking_id") or obj.get("client_reference_id") or 0)
        b = get_booking(conn, bid) if bid else None
        if b and b["status"] == "awaiting_payment":
            _set_status(conn, bid, "expired")
            return f"booking {bid} expired"
    elif kind == "charge.refunded":
        pi = obj.get("payment_intent")
        if pi:
            conn.execute("UPDATE bookings SET payment_status = 'refunded', refund_cents = ? WHERE stripe_payment_intent = ?",
                         (obj.get("amount_refunded", 0), pi))
            return f"refund recorded for {pi}"
    elif kind == "charge.dispute.created":
        pi = obj.get("payment_intent")
        if pi:
            conn.execute("UPDATE bookings SET payment_status = 'disputed' WHERE stripe_payment_intent = ?", (pi,))
            return f"dispute on {pi}"
    return f"ignored {kind}"
