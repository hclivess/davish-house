"""JSON API. Interactive docs are served at /docs."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from .. import bookings as booking_svc
from .. import payments, settings
from ..availability import SLOT_MINUTES, AvailabilityError, busy_ranges, check_range, free_hours_by_day
from ..deps import db, require_user
from ..timezones import local_now
from ..pricing import day_rate, quote_stay, rules_for
from ..queries import booking_detail, listing_detail, search_listings

router = APIRouter(prefix="/api", tags=["api"])
log = logging.getLogger("davish.api")


@router.get("/listings")
def api_search(
    conn: sqlite3.Connection = Depends(db),
    city: str = "", bedrooms: int = Query(-1, description="0 = studio, 3 = three or more, -1 = any"), capacity: int = 0,
    max_rate: int = Query(0, description="max hourly rate in cents"),
    checkin: str = Query("", description="YYYY-MM-DDTHH:MM"), checkout: str = Query("", description="YYYY-MM-DDTHH:MM"),
):
    return {"results": search_listings(conn, city=city, bedrooms=bedrooms, capacity=capacity, max_rate_cents=max_rate,
                                       checkin=checkin, checkout=checkout)}


@router.get("/listings/{listing_id}")
def api_listing(listing_id: int, conn: sqlite3.Connection = Depends(db)):
    l = listing_detail(conn, listing_id)
    if not l:
        raise HTTPException(404, "Listing not found")
    return l


@router.get("/listings/{listing_id}/availability")
def api_availability(listing_id: int, conn: sqlite3.Connection = Depends(db),
                     from_date: str = Query("", alias="from", description="YYYY-MM-DD, default today"),
                     days: int = Query(31, ge=1, le=120)):
    """Unavailable ranges (bookings + cleaning buffers + blocks + the past) over a window, plus a per-day summary."""
    l = booking_svc.get_listing(conn, listing_id)
    if not l:
        raise HTTPException(404, "Listing not found")
    now = local_now(l["timezone"])
    try:
        d = date.fromisoformat(from_date) if from_date else now.date()
    except ValueError:
        raise HTTPException(422, "from must be YYYY-MM-DD")
    busy = busy_ranges(conn, l, d, days, now)
    from datetime import timedelta as _td
    rules = rules_for(conn, l["id"], datetime.combine(d, datetime.min.time()), datetime.combine(d, datetime.min.time()) + _td(days=days))
    summary = free_hours_by_day(busy, d, days)
    for s in summary:
        s["hourly_rate_cents"] = day_rate(l, rules, datetime.strptime(s["date"], "%Y-%m-%d"))
    return {
        "from": d.isoformat(), "days": days,
        "now": now.strftime("%Y-%m-%dT%H:%M"),
        "slot_minutes": SLOT_MINUTES,
        "min_hours": l["min_hours"], "max_hours": l["max_hours"],
        "checkin_window": [l["checkin_from"], l["checkin_until"]], "checkout_window": [l["checkout_from"], l["checkout_until"]],
        "busy": busy,
        "days_summary": summary,
    }


@router.post("/favorites/{listing_id}/toggle")
def api_toggle_favorite(listing_id: int, conn: sqlite3.Connection = Depends(db), u: dict = Depends(require_user)):
    if not booking_svc.get_listing(conn, listing_id):
        raise HTTPException(404, "Listing not found")
    existing = conn.execute("SELECT 1 FROM favorites WHERE user_id = ? AND listing_id = ?", (u["id"], listing_id)).fetchone()
    if existing:
        conn.execute("DELETE FROM favorites WHERE user_id = ? AND listing_id = ?", (u["id"], listing_id))
    else:
        conn.execute("INSERT INTO favorites (user_id, listing_id) VALUES (?,?)", (u["id"], listing_id))
    return {"favorite": not existing}


class QuoteRequest(BaseModel):
    listing_id: int
    start_at: str = Field(..., examples=["2026-10-02T14:00"])
    end_at: str = Field(..., examples=["2026-10-02T17:00"])
    guests: int = 1


@router.post("/quote")
def api_quote(req: QuoteRequest, conn: sqlite3.Connection = Depends(db)):
    l = booking_svc.get_listing(conn, req.listing_id)
    if not l:
        raise HTTPException(404, "Listing not found")
    try:
        hours = check_range(conn, l, req.start_at, req.end_at)
    except AvailabilityError as e:
        raise HTTPException(409, str(e))
    return {"available": True, **quote_stay(conn, l, req.start_at, req.end_at, max(1, req.guests)).as_dict()}


class BookingRequest(QuoteRequest):
    note: str = ""


@router.post("/bookings", status_code=201)
def api_create_booking(req: BookingRequest, conn: sqlite3.Connection = Depends(db), u: dict = Depends(require_user)):
    try:
        b = booking_svc.create_booking(conn, req.listing_id, u["id"], req.start_at, req.end_at, req.guests, req.note)
    except booking_svc.BookingError as e:
        raise HTTPException(409, str(e))
    checkout_url = None
    if payments.configured():
        try:
            checkout_url = booking_svc.start_checkout(conn, b["id"], u["email"], settings.BASE_URL)
        except booking_svc.BookingError as e:
            raise HTTPException(502, str(e))
    return {**dict(b), "checkout_url": checkout_url}


@router.post("/bookings/{booking_id}/sync-payment")
def api_sync_payment(booking_id: int, conn: sqlite3.Connection = Depends(db), u: dict = Depends(require_user)):
    b = booking_svc.get_booking(conn, booking_id)
    if not b or u["id"] not in (b["guest_id"], b["host_id"]):
        raise HTTPException(404, "Booking not found")
    return booking_svc.sync_payment(conn, booking_id)


@router.get("/bookings/{booking_id}")
def api_booking(booking_id: int, conn: sqlite3.Connection = Depends(db), u: dict = Depends(require_user)):
    b = booking_detail(conn, booking_id)
    if not b or u["id"] not in (b["guest_id"], b["host_id"]):
        raise HTTPException(404, "Booking not found")
    return b


@router.post("/bookings/{booking_id}/cancel")
def api_cancel(booking_id: int, conn: sqlite3.Connection = Depends(db), u: dict = Depends(require_user)):
    try:
        return booking_svc.cancel(conn, booking_id, u["id"])
    except booking_svc.BookingError as e:
        raise HTTPException(409, str(e))


@router.get("/me")
def api_me(u: dict = Depends(require_user)):
    return u


webhook_router = APIRouter(tags=["stripe"])


@webhook_router.post("/stripe/webhook", include_in_schema=False)
async def stripe_webhook(request: Request, conn: sqlite3.Connection = Depends(db), stripe_signature: str = Header("")):
    payload = await request.body()
    try:
        event = payments.parse_webhook(payload, stripe_signature)
    except payments.PaymentError as e:
        raise HTTPException(400, str(e))
    try:
        result = booking_svc.handle_webhook_event(conn, event)
    except Exception:  # noqa: BLE001 - always ack so Stripe doesn't retry forever; the return-page sync is the fallback
        log.exception("webhook handling failed for %s", event.get("id"))
        result = "error"
    log.info("stripe %s: %s", event.get("type"), result)
    return {"received": True, "result": result}


@router.get("/health")
def health():
    return {"ok": True, "time": datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ")}
