"""Email notifications for booking events. Text is translated in the current request language."""
from __future__ import annotations

import sqlite3

from . import mailer, settings
from .db import row
from .i18n import _


def _ctx(conn: sqlite3.Connection, booking_id: int) -> dict | None:
    return row(conn, """SELECT b.*, l.title, l.address, l.checkin_instructions, g.email AS guest_email, g.name AS guest_name,
                        h.email AS host_email, h.name AS host_name
                        FROM bookings b JOIN listings l ON l.id = b.listing_id JOIN users g ON g.id = b.guest_id JOIN users h ON h.id = l.host_id
                        WHERE b.id = ?""", (booking_id,))


def _when(b: dict) -> str:
    return f"{b['start_at'].replace('T', ' ')} → {b['end_at'].replace('T', ' ')}"


def _link(b: dict) -> str:
    return f"{settings.BASE_URL}/bookings/{b['id']}"


def booking_confirmed(conn: sqlite3.Connection, booking_id: int) -> None:
    b = _ctx(conn, booking_id)
    if not b:
        return
    extra = ""
    if b["address"] or b["checkin_instructions"]:
        extra = "\n" + _("Address: %s") % b["address"] + "\n" + (b["checkin_instructions"] or "") + "\n"
    mailer.send(b["guest_email"], _("Booking confirmed: %s") % b["title"],
                _("Hi %s,\n\nYour booking is confirmed.\n%s\n%s\n%s\nDetails: %s\n") % (b["guest_name"], b["title"], _when(b), extra, _link(b)))
    mailer.send(b["host_email"], _("New booking: %s") % b["title"],
                _("Hi %s,\n\n%s booked %s.\n%s\nPayout: %s\nDetails: %s\n") % (b["host_name"], b["guest_name"], b["title"], _when(b),
                                                                             f"${b['host_payout_cents'] / 100:.2f}", _link(b)))


def booking_requested(conn: sqlite3.Connection, booking_id: int) -> None:
    b = _ctx(conn, booking_id)
    if not b:
        return
    mailer.send(b["host_email"], _("Booking request: %s") % b["title"],
                _("Hi %s,\n\n%s requested %s.\n%s\nAccept or decline here: %s\n") % (b["host_name"], b["guest_name"], b["title"], _when(b), _link(b)))
    mailer.send(b["guest_email"], _("Request sent: %s") % b["title"],
                _("Hi %s,\n\nYour request was sent to %s. You'll hear back soon.\n%s\nDetails: %s\n") % (b["guest_name"], b["host_name"], _when(b), _link(b)))


def request_answered(conn: sqlite3.Connection, booking_id: int, accepted: bool) -> None:
    b = _ctx(conn, booking_id)
    if not b:
        return
    if accepted:
        booking_confirmed(conn, booking_id)
    else:
        mailer.send(b["guest_email"], _("Request declined: %s") % b["title"],
                    _("Hi %s,\n\n%s couldn't accept your request for %s. Your card was not charged.\nFind another apartment: %s\n")
                    % (b["guest_name"], b["host_name"], _when(b), settings.BASE_URL + "/search"))


def booking_cancelled(conn: sqlite3.Connection, booking_id: int, by_host: bool) -> None:
    b = _ctx(conn, booking_id)
    if not b:
        return
    refund = f"${b['refund_cents'] / 100:.2f}"
    mailer.send(b["guest_email"], _("Booking cancelled: %s") % b["title"],
                _("Hi %s,\n\nThe booking %s (%s) was cancelled%s. Refund: %s.\nDetails: %s\n")
                % (b["guest_name"], b["title"], _when(b), _(" by the host") if by_host else "", refund, _link(b)))
    mailer.send(b["host_email"], _("Booking cancelled: %s") % b["title"],
                _("Hi %s,\n\nThe booking %s (%s) was cancelled%s.\nDetails: %s\n")
                % (b["host_name"], b["title"], _when(b), _(" by the guest") if not by_host else "", _link(b)))


def new_message(conn: sqlite3.Connection, booking_id: int, sender_id: int, body: str) -> None:
    b = _ctx(conn, booking_id)
    if not b:
        return
    to_host = sender_id == b["guest_id"]
    mailer.send(b["host_email"] if to_host else b["guest_email"], _("New message about %s") % b["title"],
                _("%s wrote:\n\n%s\n\nReply here: %s\n") % (b["guest_name"] if to_host else b["host_name"], body, _link(b) + "#messages"))
