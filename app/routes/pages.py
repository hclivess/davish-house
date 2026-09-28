"""Server-rendered pages: browsing, booking, trips, auth, account, host tools."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import bookings as booking_svc
from .. import mailer, notify, payments, photos, settings
from ..auth import (SESSION_COOKIE, consume_reset_token, create_reset_token, hash_password, peek_reset_token,
                    set_session_cookie, verify_password)
from ..availability import busy_ranges, free_hours_by_day
from ..catalog import AMENITIES
from ..pricing import POLICIES, day_rate, rules_for
from ..db import row, rows, transaction
from ..deps import db, render, user
from ..i18n import _
from ..queries import (LISTING_CARD_SQL, admin_overview, booking_detail, host_bookings, host_payouts, host_stats, listing_detail,
                       public_profile, search_listings, user_favorites, user_trips)
from ..timezones import COMMON_TIMEZONES, local_now, valid as valid_tz

router = APIRouter()
HHMM = {f"{h:02d}:00" for h in range(25)}


def _redirect(url: str, status_code: int = 303) -> RedirectResponse:
    return RedirectResponse(url, status_code=status_code)


def _login_redirect(request: Request) -> RedirectResponse:
    return _redirect("/login?" + urlencode({"next": str(request.url.path)}))


def default_window(tz: str | None = None, hours: int | None = None, notice_hours: int = 1) -> dict:
    """Default search window: check-in one hour from now (rounded up to the hour), `hours` long. May cross midnight.
    Listings with a longer advance-notice rule push the default check-in out accordingly."""
    hours = hours or settings.DEFAULT_STAY_HOURS
    now = local_now(tz or settings.DEFAULT_TZ)
    start = now + timedelta(hours=max(1, notice_hours))
    if start.minute:
        start = start.replace(minute=0) + timedelta(hours=1)
    end = start + timedelta(hours=hours)
    return {"date": start.strftime("%Y-%m-%d"), "start": start.strftime("%H:%M"),
            "end_date": end.strftime("%Y-%m-%d"), "end": end.strftime("%H:%M")}


def _int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _window_from_query(date_: str, start: str, end_date: str, end: str) -> tuple[str, str]:
    """Compose check-in / check-out ISO strings from the four search fields. Empty strings when incomplete."""
    if not (date_ and start and end):
        return "", ""
    return f"{date_}T{start}", f"{end_date or date_}T{end}"


# ---------------------------------------------------------------- browsing


@router.get("/", response_class=HTMLResponse)
def home(request: Request, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user)):
    booking_svc.complete_past(conn)
    featured = rows(conn, LISTING_CARD_SQL + " WHERE l.status = 'active' ORDER BY l.city = 'Mérida' DESC, l.id")
    cities = rows(conn, "SELECT city, COUNT(*) AS n FROM listings WHERE status = 'active' GROUP BY city ORDER BY n DESC LIMIT 6")
    q = {"city": "", "capacity": "", "bedrooms": "", **default_window()}
    return render(request, "home.html", {"user": u, "featured": featured, "cities": cities, "q": q, "auto_window": True,
                                         "today": q["date"]})


@router.get("/search", response_class=HTMLResponse)
def search(
    request: Request, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user),
    city: str = "", bedrooms: str = "", capacity: str = "", max_rate: str = "", min_rate: str = "",
    date: str = "", start: str = "", end_date: str = "", end: str = "", instant: str = "", sort: str = "recommended",
):
    booking_svc.complete_past(conn)
    bedrooms, capacity, max_rate, min_rate, instant = (_int(bedrooms, -1), _int(capacity, 0), _int(max_rate, 0), _int(min_rate, 0), _int(instant, 0))
    amenities = [a for a in request.query_params.getlist("amenity") if a in AMENITIES]
    explicit_window = bool(date and start and end)
    if not date and not start and not end:   # prefill the form, but list everything until a window is submitted
        d = default_window()
        date, start, end_date, end = d["date"], d["start"], d["end_date"], d["end"]
    checkin, checkout = _window_from_query(date, start, end_date, end) if explicit_window else ("", "")
    results = search_listings(conn, city=city, bedrooms=bedrooms, capacity=capacity, max_rate_cents=max_rate * 100, min_rate_cents=min_rate * 100,
                              checkin=checkin, checkout=checkout, amenities=amenities, instant_only=bool(instant), sort=sort,
                              user_id=u["id"] if u else None)
    q = {"city": city, "bedrooms": bedrooms if bedrooms >= 0 else "", "capacity": capacity or "", "max_rate": max_rate or "", "min_rate": min_rate or "",
         "date": date, "start": start, "end_date": end_date or date, "end": end, "instant": instant or "", "sort": sort if sort != "recommended" else ""}
    q_links = {**q, "date": date if explicit_window else "", "start": start if explicit_window else "", "end_date": end_date if explicit_window else "", "end": end if explicit_window else ""}
    return render(request, "search.html", {"user": u, "results": results, "q": q, "q_links": q_links, "today": default_window()["date"],
                                           "checkin": checkin, "checkout": checkout, "amenities": amenities})


def _listing_ctx(conn, u, l, checkin="", checkout="", error=None):
    now = local_now(l["timezone"])
    today = now.date()
    if not checkin:
        w = default_window(l["timezone"], hours=max(settings.DEFAULT_STAY_HOURS, int(l["min_hours"])), notice_hours=l.get("advance_notice_hours") or 1)
        checkin, checkout = f"{w['date']}T{w['start']}", f"{w['end_date']}T{w['end']}"
    busy = busy_ranges(conn, l, today, 62, now)
    days = free_hours_by_day(busy, today, 62)
    rules = rules_for(conn, l["id"], datetime.combine(today, datetime.min.time()), datetime.combine(today, datetime.min.time()) + timedelta(days=62))
    for d in days:
        d["rate"] = day_rate(l, rules, datetime.strptime(d["date"], "%Y-%m-%d"))
    is_fav = bool(u and row(conn, "SELECT 1 AS x FROM favorites WHERE user_id = ? AND listing_id = ?", (u["id"], l["id"])))
    return {"user": u, "l": l, "checkin": checkin, "checkout": checkout, "today": today.isoformat(),
            "max_date": (today + timedelta(days=min(365, l["max_advance_days"] or 365))).isoformat(), "error": error, "days": days,
            "is_favorite": is_fav, "policy": POLICIES[l["cancellation_policy"]] if l["cancellation_policy"] in POLICIES else POLICIES["flexible"]}


@router.get("/listings/{listing_id}", response_class=HTMLResponse)
def listing_page(request: Request, listing_id: int, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user),
                 date: str = "", start: str = "", end_date: str = "", end: str = ""):
    booking_svc.complete_past(conn)
    l = listing_detail(conn, listing_id)
    if not l or (l["status"] != "active" and (not u or u["id"] != l["host_id"])):
        return render(request, "error.html", {"user": u, "message": "Listing not found."}, 404)
    checkin, checkout = _window_from_query(date, start, end_date, end)
    return render(request, "listing.html", _listing_ctx(conn, u, l, checkin, checkout))


# ---------------------------------------------------------------- booking


@router.post("/listings/{listing_id}/book")
def book(request: Request, listing_id: int, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user),
         start_at: str = Form(...), end_at: str = Form(...), guests: int = Form(1), note: str = Form("")):
    if not u:
        return _login_redirect(request)
    try:
        b = booking_svc.create_booking(conn, listing_id, u["id"], start_at, end_at, guests, note)
    except booking_svc.BookingError as e:
        l = listing_detail(conn, listing_id)
        if not l:
            return render(request, "error.html", {"user": u, "message": "Listing not found."}, 404)
        return render(request, "listing.html", _listing_ctx(conn, u, l, start_at, end_at, str(e)), 409)
    if payments.configured():
        try:
            return _redirect(booking_svc.start_checkout(conn, b["id"], u["email"], settings.BASE_URL))
        except booking_svc.BookingError as e:
            return render(request, "error.html", {"user": u, "message": str(e), "link": ("View booking", f"/bookings/{b['id']}")}, 502)
    return _redirect(f"/bookings/{b['id']}?new=1")


@router.get("/bookings/{booking_id}/pay")
def pay_booking(request: Request, booking_id: int, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user)):
    """Re-open Stripe Checkout for a booking that is still awaiting payment."""
    if not u:
        return _login_redirect(request)
    b = booking_svc.get_booking(conn, booking_id)
    if not b or b["guest_id"] != u["id"]:
        return render(request, "error.html", {"user": u, "message": "Booking not found."}, 404)
    b = booking_svc.sync_payment(conn, booking_id)
    if b["status"] != "awaiting_payment":
        return _redirect(f"/bookings/{booking_id}")
    try:
        return _redirect(booking_svc.start_checkout(conn, booking_id, u["email"], settings.BASE_URL))
    except booking_svc.BookingError as e:
        return render(request, "error.html", {"user": u, "message": str(e)}, 502)


@router.get("/bookings/{booking_id}", response_class=HTMLResponse)
def booking_page(request: Request, booking_id: int, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user),
                 new: int = 0, paid: int = 0, cancelled: int = 0):
    if not u:
        return _login_redirect(request)
    booking_svc.complete_past(conn)
    if paid:  # back from Stripe: don't wait for the webhook
        booking_svc.sync_payment(conn, booking_id)
    b = booking_detail(conn, booking_id)
    if not b or (u["id"] not in (b["guest_id"], b["host_id"]) and not u.get("is_admin")):
        return render(request, "error.html", {"user": u, "message": "Booking not found."}, 404)
    return render(request, "booking.html", {"user": u, "b": b, "is_new": bool(new or paid), "is_host": u["id"] == b["host_id"] or (u.get("is_admin") and u["id"] != b["guest_id"]),
                                            "payment_cancelled": bool(cancelled), "stripe": payments.configured()})


@router.post("/bookings/{booking_id}/cancel")
def cancel_booking(request: Request, booking_id: int, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user)):
    if not u:
        return _login_redirect(request)
    try:
        booking_svc.cancel(conn, booking_id, u["id"])
    except booking_svc.BookingError as e:
        return render(request, "error.html", {"user": u, "message": str(e)}, 409)
    return _redirect(f"/bookings/{booking_id}")


@router.post("/bookings/{booking_id}/respond")
def respond_booking(request: Request, booking_id: int, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user),
                    action: str = Form(...)):
    if not u:
        return _login_redirect(request)
    try:
        booking_svc.host_respond(conn, booking_id, u["id"], accept=(action == "accept"))
    except booking_svc.BookingError as e:
        return render(request, "error.html", {"user": u, "message": str(e)}, 409)
    return _redirect(f"/bookings/{booking_id}")


@router.post("/bookings/{booking_id}/messages")
def post_message(request: Request, booking_id: int, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user),
                 body: str = Form(...)):
    if not u:
        return _login_redirect(request)
    b = booking_detail(conn, booking_id)
    if not b or u["id"] not in (b["guest_id"], b["host_id"]):
        return render(request, "error.html", {"user": u, "message": "Booking not found."}, 404)
    if body.strip():
        conn.execute("INSERT INTO messages (booking_id, sender_id, body) VALUES (?,?,?)", (booking_id, u["id"], body.strip()[:2000]))
        notify.new_message(conn, booking_id, u["id"], body.strip()[:2000])
    return _redirect(f"/bookings/{booking_id}#messages")


@router.post("/bookings/{booking_id}/review")
def post_review(request: Request, booking_id: int, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user),
                rating: int = Form(...), body: str = Form(""), cleanliness: int = Form(0), accuracy: int = Form(0),
                communication: int = Form(0), location: int = Form(0), value: int = Form(0)):
    if not u:
        return _login_redirect(request)
    b = booking_detail(conn, booking_id)
    if not b or b["guest_id"] != u["id"] or b["status"] != "completed" or b["review_id"]:
        return render(request, "error.html", {"user": u, "message": "You can only review a completed stay once."}, 409)
    clamp = lambda v: max(1, min(5, v)) if v else None  # noqa: E731
    conn.execute("""INSERT INTO reviews (booking_id, listing_id, author_id, rating, body, cleanliness, accuracy, communication, location, value)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""",
                 (booking_id, b["listing_id"], u["id"], max(1, min(5, rating)), body.strip()[:2000], clamp(cleanliness), clamp(accuracy),
                  clamp(communication), clamp(location), clamp(value)))
    return _redirect(f"/listings/{b['listing_id']}#reviews")


@router.post("/bookings/{booking_id}/guest-review")
def post_guest_review(request: Request, booking_id: int, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user),
                      rating: int = Form(...), body: str = Form("")):
    if not u:
        return _login_redirect(request)
    b = booking_detail(conn, booking_id)
    if not b or b["host_id"] != u["id"] or b["status"] != "completed" or b["guest_review_id"]:
        return render(request, "error.html", {"user": u, "message": "You can only review a guest after a completed stay, once."}, 409)
    conn.execute("INSERT INTO guest_reviews (booking_id, guest_id, host_id, rating, body) VALUES (?,?,?,?,?)",
                 (booking_id, b["guest_id"], u["id"], max(1, min(5, rating)), body.strip()[:2000]))
    return _redirect(f"/bookings/{booking_id}")


@router.post("/reviews/{review_id}/reply")
def reply_review(request: Request, review_id: int, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user), body: str = Form(...)):
    if not u:
        return _login_redirect(request)
    r = row(conn, "SELECT r.id, r.listing_id, l.host_id FROM reviews r JOIN listings l ON l.id = r.listing_id WHERE r.id = ?", (review_id,))
    if not r or r["host_id"] != u["id"]:
        return render(request, "error.html", {"user": u, "message": "Review not found."}, 404)
    conn.execute("UPDATE reviews SET host_reply = ?, host_reply_at = strftime('%Y-%m-%dT%H:%M', 'now') WHERE id = ?", (body.strip()[:2000], review_id))
    return _redirect(f"/listings/{r['listing_id']}#reviews")


# ---------------------------------------------------------------- favorites & profiles


@router.get("/favorites", response_class=HTMLResponse)
def favorites_page(request: Request, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user)):
    if not u:
        return _login_redirect(request)
    return render(request, "favorites.html", {"user": u, "results": user_favorites(conn, u["id"]), "q": None})


@router.post("/favorites/{listing_id}/toggle")
def toggle_favorite(request: Request, listing_id: int, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user), next: str = Form("/")):
    if not u:
        return _login_redirect(request)
    if row(conn, "SELECT 1 AS x FROM favorites WHERE user_id = ? AND listing_id = ?", (u["id"], listing_id)):
        conn.execute("DELETE FROM favorites WHERE user_id = ? AND listing_id = ?", (u["id"], listing_id))
    elif row(conn, "SELECT id FROM listings WHERE id = ?", (listing_id,)):
        conn.execute("INSERT INTO favorites (user_id, listing_id) VALUES (?,?)", (u["id"], listing_id))
    return _redirect(next if next.startswith("/") else "/")


@router.get("/users/{user_id}", response_class=HTMLResponse)
def profile_page(request: Request, user_id: int, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user)):
    p = public_profile(conn, user_id)
    if not p:
        return render(request, "error.html", {"user": u, "message": "User not found."}, 404)
    return render(request, "profile.html", {"user": u, "p": p, "q": None})


@router.get("/trips", response_class=HTMLResponse)
def trips(request: Request, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user)):
    if not u:
        return _login_redirect(request)
    booking_svc.complete_past(conn)
    all_trips = user_trips(conn, u["id"])
    upcoming = [t for t in all_trips if t["status"] in booking_svc.ACTIVE]
    past = [t for t in all_trips if t["status"] not in booking_svc.ACTIVE]
    return render(request, "trips.html", {"user": u, "upcoming": upcoming, "past": past})


# ---------------------------------------------------------------- auth


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, u: dict | None = Depends(user), next: str = "/"):
    if u:
        return _redirect(next)
    return render(request, "login.html", {"user": None, "next": next})


@router.post("/login")
def login(request: Request, conn: sqlite3.Connection = Depends(db), email: str = Form(...), password: str = Form(...), next: str = Form("/")):
    acct = row(conn, "SELECT * FROM users WHERE email = ?", (email.strip(),))
    if not acct or not verify_password(password, acct["password_hash"]):
        return render(request, "login.html", {"user": None, "next": next, "error": "Wrong email or password."}, 401)
    if acct["is_banned"]:
        return render(request, "login.html", {"user": None, "next": next, "error": "This account has been suspended."}, 403)
    resp = _redirect(next if next.startswith("/") else "/")
    set_session_cookie(resp, acct["id"])
    return resp


@router.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request, u: dict | None = Depends(user), next: str = "/", host: int = 0):
    if u:
        return _redirect(next)
    return render(request, "signup.html", {"user": None, "next": next, "host": host})


@router.post("/signup")
def signup(request: Request, conn: sqlite3.Connection = Depends(db), name: str = Form(...), email: str = Form(...),
           password: str = Form(...), is_host: int = Form(0), next: str = Form("/")):
    name, email = name.strip(), email.strip().lower()
    err = None
    if len(password) < 8:
        err = "Password must be at least 8 characters."
    elif "@" not in email or not name:
        err = "Please enter your name and a valid email."
    elif row(conn, "SELECT id FROM users WHERE email = ?", (email,)):
        err = "An account with that email already exists."
    if err:
        return render(request, "signup.html", {"user": None, "next": next, "host": is_host, "error": err}, 400)
    cur = conn.execute("INSERT INTO users (email, password_hash, name, is_host) VALUES (?,?,?,?)",
                       (email, hash_password(password), name, 1 if is_host else 0))
    mailer.send(email, _("Welcome to %s") % settings.SITE_NAME,
                _("Hi %s,\n\nYour %s account is ready. Browse apartments at %s\n") % (name, settings.SITE_NAME, settings.BASE_URL + "/search"))
    resp = _redirect("/host" if is_host else (next if next.startswith("/") else "/"))
    set_session_cookie(resp, cur.lastrowid)
    return resp


@router.post("/logout")
def logout():
    resp = _redirect("/")
    resp.delete_cookie(SESSION_COOKIE)
    return resp


@router.get("/forgot", response_class=HTMLResponse)
def forgot_page(request: Request, u: dict | None = Depends(user)):
    return render(request, "forgot.html", {"user": u})


@router.post("/forgot")
def forgot(request: Request, conn: sqlite3.Connection = Depends(db), email: str = Form(...)):
    acct = row(conn, "SELECT id, name, email FROM users WHERE email = ?", (email.strip(),))
    if acct:
        token = create_reset_token(conn, acct["id"])
        link = f"{settings.BASE_URL}/reset/{token}"
        mailer.send(acct["email"], _("Reset your %s password") % settings.SITE_NAME,
                    _("Hi %s,\n\nUse this link within 60 minutes to choose a new password:\n%s\n\nIf you didn't ask for this, ignore this email.\n") % (acct["name"], link))
    return render(request, "forgot.html", {"user": None, "sent": True, "email": email.strip()})


@router.get("/reset/{token}", response_class=HTMLResponse)
def reset_page(request: Request, token: str, conn: sqlite3.Connection = Depends(db)):
    if not peek_reset_token(conn, token):
        return render(request, "error.html", {"user": None, "message": "This reset link is invalid or has expired.",
                                              "link": ("Request a new one", "/forgot")}, 400)
    return render(request, "reset.html", {"user": None, "token": token})


@router.post("/reset/{token}")
def reset(request: Request, token: str, conn: sqlite3.Connection = Depends(db), password: str = Form(...), confirm: str = Form("")):
    if len(password) < 8 or password != confirm:
        return render(request, "reset.html", {"user": None, "token": token, "error": "Passwords must match and be at least 8 characters."}, 400)
    uid = consume_reset_token(conn, token)
    if not uid:
        return render(request, "error.html", {"user": None, "message": "This reset link is invalid or has expired.",
                                              "link": ("Request a new one", "/forgot")}, 400)
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(password), uid))
    resp = _redirect("/account?reset=1")
    set_session_cookie(resp, uid)
    return resp


@router.get("/account", response_class=HTMLResponse)
def account_page(request: Request, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user), reset: int = 0, saved: int = 0):
    if not u:
        return _login_redirect(request)
    return render(request, "account.html", {"user": u, "reset": reset, "saved": saved})


@router.post("/account")
async def account_update(request: Request, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user),
                         name: str = Form(...), email: str = Form(...), current_password: str = Form(""), new_password: str = Form(""),
                         bio: str = Form(""), phone: str = Form("")):
    if not u:
        return _login_redirect(request)
    form = await request.form()
    avatar = form.get("avatar")
    if avatar is not None and getattr(avatar, "filename", ""):
        try:
            url = photos.save_upload(0, await avatar.read())  # listing 0 = avatars folder
        except photos.PhotoError as e:
            return render(request, "account.html", {"user": u, "error": str(e)}, 400)
        photos.delete_file(u["avatar_url"])
        conn.execute("UPDATE users SET avatar_url = ? WHERE id = ?", (url, u["id"]))
    conn.execute("UPDATE users SET bio = ?, phone = ? WHERE id = ?", (bio.strip()[:1000], phone.strip()[:40], u["id"]))
    name, email = name.strip()[:80], email.strip().lower()
    if not name or "@" not in email:
        return render(request, "account.html", {"user": u, "error": "Name and a valid email are required."}, 400)
    if row(conn, "SELECT id FROM users WHERE email = ? AND id != ?", (email, u["id"])):
        return render(request, "account.html", {"user": u, "error": "That email is already in use."}, 400)
    if new_password:
        acct = row(conn, "SELECT password_hash FROM users WHERE id = ?", (u["id"],))
        if not verify_password(current_password, acct["password_hash"]):
            return render(request, "account.html", {"user": u, "error": "Current password is wrong."}, 400)
        if len(new_password) < 8:
            return render(request, "account.html", {"user": u, "error": "New password must be at least 8 characters."}, 400)
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new_password), u["id"]))
    conn.execute("UPDATE users SET name = ?, email = ? WHERE id = ?", (name, email, u["id"]))
    return _redirect("/account?saved=1")


@router.post("/account/delete")
def account_delete(request: Request, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user), password: str = Form(...)):
    if not u:
        return _login_redirect(request)
    acct = row(conn, "SELECT password_hash FROM users WHERE id = ?", (u["id"],))
    if not verify_password(password, acct["password_hash"]):
        return render(request, "account.html", {"user": u, "error": "Password is wrong."}, 400)
    active = row(conn, """SELECT COUNT(*) AS n FROM bookings b JOIN listings l ON l.id = b.listing_id
                          WHERE b.status IN ('awaiting_payment','pending','confirmed') AND (b.guest_id = ? OR l.host_id = ?)""", (u["id"], u["id"]))
    if active["n"]:
        return render(request, "account.html", {"user": u, "error": "Cancel or complete your active bookings before deleting the account."}, 400)
    conn.execute("UPDATE listings SET status = 'paused' WHERE host_id = ?", (u["id"],))
    conn.execute("UPDATE users SET email = ?, name = 'Deleted user', password_hash = 'deleted', is_host = 0 WHERE id = ?",
                 (f"deleted-{u['id']}@invalid.local", u["id"]))
    resp = _redirect("/")
    resp.delete_cookie(SESSION_COOKIE)
    return resp


# ---------------------------------------------------------------- host tools


def _host_guard(request: Request, u: dict | None):
    if not u:
        return _login_redirect(request)
    if not u["is_host"]:
        return render(request, "error.html", {"user": u, "message": "Switch to a host account to access hosting tools.",
                                              "action": ("Become a host", "/host/become")}, 403)
    return None


def _own_listing(conn, u, listing_id):
    """A host's own listing, or any listing for an admin."""
    if u.get("is_admin"):
        return row(conn, "SELECT * FROM listings WHERE id = ?", (listing_id,))
    return row(conn, "SELECT * FROM listings WHERE id = ? AND host_id = ?", (listing_id, u["id"]))


@router.post("/host/become")
def become_host(request: Request, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user)):
    if not u:
        return _login_redirect(request)
    conn.execute("UPDATE users SET is_host = 1 WHERE id = ?", (u["id"],))
    return _redirect("/host")


@router.get("/host", response_class=HTMLResponse)
def host_dashboard(request: Request, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user)):
    if (g := _host_guard(request, u)):
        return g
    booking_svc.complete_past(conn)
    if u.get("is_admin"):   # admins manage every listing on the platform
        listings = rows(conn, LISTING_CARD_SQL + " ORDER BY l.host_id, l.id")
        return render(request, "host/dashboard.html", {
            "user": u, "listings": listings, "stats": host_stats(conn, None), "bookings": host_bookings(conn, None)[:12], "all_hosts": True,
        })
    listings = rows(conn, LISTING_CARD_SQL + " WHERE l.host_id = ? ORDER BY l.id DESC", (u["id"],))
    return render(request, "host/dashboard.html", {
        "user": u, "listings": listings, "stats": host_stats(conn, u["id"]), "bookings": host_bookings(conn, u["id"])[:12],
    })


@router.get("/host/bookings", response_class=HTMLResponse)
def host_bookings_page(request: Request, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user), status: str = ""):
    if (g := _host_guard(request, u)):
        return g
    booking_svc.complete_past(conn)
    return render(request, "host/bookings.html", {"user": u, "bookings": host_bookings(conn, None if u.get("is_admin") else u["id"], status or None), "status": status})


def _listing_form_ctx(conn, u, l=None, error=None):
    amenities: set[str] = set()
    blocks: list[dict] = []
    if l:
        amenities = {a["amenity"] for a in rows(conn, "SELECT amenity FROM listing_amenities WHERE listing_id = ?", (l["id"],))}
        blocks = rows(conn, "SELECT * FROM availability_blocks WHERE listing_id = ? AND end_at >= ? ORDER BY start_at",
                      (l["id"], local_now(l["timezone"]).strftime("%Y-%m-%dT%H:%M")))
        l = dict(l)
        l["photo_rows"] = rows(conn, "SELECT id, url, sort FROM listing_photos WHERE listing_id = ? ORDER BY sort, id", (l["id"],))
    return {"user": u, "l": l, "selected_amenities": amenities, "blocks": blocks, "error": error,
            "timezones": COMMON_TIMEZONES, "default_tz": settings.DEFAULT_TZ, "hours": [f"{h:02d}:00" for h in range(25)],
            "max_photos": settings.MAX_PHOTOS}


@router.get("/host/listings/new", response_class=HTMLResponse)
def new_listing(request: Request, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user)):
    if (g := _host_guard(request, u)):
        return g
    return render(request, "host/listing_form.html", _listing_form_ctx(conn, u))


@router.get("/host/listings/{listing_id}/edit", response_class=HTMLResponse)
def edit_listing(request: Request, listing_id: int, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user)):
    if (g := _host_guard(request, u)):
        return g
    l = _own_listing(conn, u, listing_id)
    if not l:
        return render(request, "error.html", {"user": u, "message": "Listing not found."}, 404)
    return render(request, "host/listing_form.html", _listing_form_ctx(conn, u, l))


async def _parse_listing_form(request: Request):
    """Returns (data, amenities, uploaded_files, error)."""
    form = await request.form()

    def g(k, default=""):
        v = form.get(k)
        return v.strip() if isinstance(v, str) else default

    try:
        data = {
            "title": g("title")[:120], "description": g("description")[:5000], "category": "apartment",
            "bedrooms": max(0, int(g("bedrooms", "1"))), "bathrooms": max(0.5, float(g("bathrooms", "1"))), "beds": max(0, int(g("beds", "1"))),
            "size_m2": int(g("size_m2")) if g("size_m2") else None, "floor": g("floor")[:40],
            "city": g("city")[:80], "neighborhood": g("neighborhood")[:80], "address": g("address")[:200],
            "capacity": max(1, int(g("capacity", "1"))),
            "hourly_rate_cents": int(round(float(g("hourly_rate", "0")) * 100)),
            "daily_rate_cents": int(round(float(g("daily_rate") or "0") * 100)),
            "cleaning_fee_cents": int(round(float(g("cleaning_fee") or "0") * 100)),
            "min_hours": float(g("min_hours", "1")), "max_hours": float(g("max_hours", "720")),
            "buffer_minutes": int(g("buffer_minutes", "60")), "instant_book": 1 if form.get("instant_book") else 0,
            "status": "active" if g("status", "active") == "active" else "paused",
            "timezone": g("timezone", settings.DEFAULT_TZ),
            "checkin_from": g("checkin_from", "00:00"), "checkin_until": g("checkin_until", "24:00"),
            "checkout_from": g("checkout_from", "00:00"), "checkout_until": g("checkout_until", "24:00"),
            "house_rules": g("house_rules")[:3000], "checkin_instructions": g("checkin_instructions")[:3000],
            "weekend_hourly_rate_cents": int(round(float(g("weekend_hourly_rate") or "0") * 100)),
            "long_stay_discount_pct": max(0, min(90, int(g("long_stay_discount_pct") or "0"))),
            "advance_notice_hours": max(0, int(g("advance_notice_hours") or "0")),
            "max_advance_days": max(1, min(730, int(g("max_advance_days") or "365"))),
            "cancellation_policy": g("cancellation_policy", "flexible") if g("cancellation_policy", "flexible") in POLICIES else "flexible",
            "monthly_rate_cents": int(round(float(g("monthly_rate") or "0") * 100)),
            "included_guests": max(0, int(g("included_guests") or "0")),
            "extra_guest_fee_cents": int(round(float(g("extra_guest_fee") or "0") * 100)),
        }
    except ValueError:
        return {}, [], [], "Please check the numeric fields."
    if not data["title"] or not data["city"]:
        return {}, [], [], "Title and city are required."
    if data["hourly_rate_cents"] <= 0:
        return {}, [], [], "Hourly rate must be greater than zero."
    if data["daily_rate_cents"] and data["daily_rate_cents"] > 24 * data["hourly_rate_cents"]:
        return {}, [], [], "The daily rate should not exceed 24 times the hourly rate."
    if not valid_tz(data["timezone"]):
        return {}, [], [], "Pick a valid timezone."
    if data["min_hours"] < 1 or data["max_hours"] < data["min_hours"]:
        return {}, [], [], "Check the minimum / maximum stay."
    for k in ("checkin_from", "checkin_until", "checkout_from", "checkout_until"):
        if data[k] not in HHMM:
            return {}, [], [], "Check-in / check-out hours must be on the hour."
    amenities = [a for a in form.getlist("amenities") if a in AMENITIES]
    files = []
    for f in form.getlist("photos"):
        if hasattr(f, "read") and getattr(f, "filename", ""):
            files.append(await f.read())
    return data, amenities, files, None


def _save_listing(conn, listing_id: int | None, host_id: int, data, amenities) -> int:
    with transaction(conn):
        if listing_id is None:
            cols = ", ".join(data.keys())
            qs = ", ".join("?" * len(data))
            cur = conn.execute(f"INSERT INTO listings (host_id, {cols}) VALUES (?, {qs})", (host_id, *data.values()))
            listing_id = cur.lastrowid
        else:
            sets = ", ".join(f"{k} = ?" for k in data)
            conn.execute(f"UPDATE listings SET {sets} WHERE id = ?", (*data.values(), listing_id))
            conn.execute("DELETE FROM listing_amenities WHERE listing_id = ?", (listing_id,))
        conn.executemany("INSERT INTO listing_amenities (listing_id, amenity) VALUES (?,?)", [(listing_id, a) for a in amenities])
    return listing_id


def _store_photos(conn, listing_id: int, files: list[bytes]) -> str | None:
    """Save uploads after the listing row exists. Returns an error message for the first bad file, if any."""
    count = row(conn, "SELECT COUNT(*) AS n FROM listing_photos WHERE listing_id = ?", (listing_id,))["n"]
    err = None
    for data in files:
        if count >= settings.MAX_PHOTOS:
            err = err or "Photo limit reached."
            break
        try:
            url = photos.save_upload(listing_id, data)
        except photos.PhotoError as e:
            err = err or str(e)
            continue
        conn.execute("INSERT INTO listing_photos (listing_id, url, sort) VALUES (?,?,?)", (listing_id, url, count))
        count += 1
    return err


@router.post("/host/listings/new")
async def create_listing(request: Request, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user)):
    if (g := _host_guard(request, u)):
        return g
    data, amenities, files, err = await _parse_listing_form(request)
    if err:
        return render(request, "host/listing_form.html", _listing_form_ctx(conn, u, None, err), 400)
    lid = _save_listing(conn, None, u["id"], data, amenities)
    _store_photos(conn, lid, files)
    return _redirect(f"/host/listings/{lid}/edit#photos" if not files else f"/listings/{lid}")


@router.post("/host/listings/{listing_id}/edit")
async def update_listing(request: Request, listing_id: int, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user)):
    if (g := _host_guard(request, u)):
        return g
    l = _own_listing(conn, u, listing_id)
    if not l:
        return render(request, "error.html", {"user": u, "message": "Listing not found."}, 404)
    data, amenities, files, err = await _parse_listing_form(request)
    if err:
        return render(request, "host/listing_form.html", _listing_form_ctx(conn, u, l, err), 400)
    _save_listing(conn, listing_id, u["id"], data, amenities)
    err = _store_photos(conn, listing_id, files)
    if err:
        return render(request, "host/listing_form.html", _listing_form_ctx(conn, u, _own_listing(conn, u, listing_id), err), 400)
    return _redirect(f"/listings/{listing_id}")


@router.post("/host/listings/{listing_id}/photos")
async def upload_photos(request: Request, listing_id: int, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user)):
    if (g := _host_guard(request, u)):
        return g
    l = _own_listing(conn, u, listing_id)
    if not l:
        return render(request, "error.html", {"user": u, "message": "Listing not found."}, 404)
    form = await request.form()
    files = [await f.read() for f in form.getlist("photos") if hasattr(f, "read") and getattr(f, "filename", "")]
    err = _store_photos(conn, listing_id, files)
    if err:
        return render(request, "host/listing_form.html", _listing_form_ctx(conn, u, l, err), 400)
    return _redirect(f"/host/listings/{listing_id}/edit#photos")


@router.post("/host/listings/{listing_id}/photos/{photo_id}/delete")
def delete_photo(request: Request, listing_id: int, photo_id: int, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user)):
    if (g := _host_guard(request, u)):
        return g
    if _own_listing(conn, u, listing_id):
        p = row(conn, "SELECT url FROM listing_photos WHERE id = ? AND listing_id = ?", (photo_id, listing_id))
        if p:
            conn.execute("DELETE FROM listing_photos WHERE id = ?", (photo_id,))
            photos.delete_file(p["url"])
    return _redirect(f"/host/listings/{listing_id}/edit#photos")


@router.post("/host/listings/{listing_id}/photos/{photo_id}/cover")
def set_cover_photo(request: Request, listing_id: int, photo_id: int, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user)):
    if (g := _host_guard(request, u)):
        return g
    if _own_listing(conn, u, listing_id):
        ids = [p["id"] for p in rows(conn, "SELECT id FROM listing_photos WHERE listing_id = ? ORDER BY sort, id", (listing_id,))]
        if photo_id in ids:
            order = [photo_id] + [i for i in ids if i != photo_id]
            conn.executemany("UPDATE listing_photos SET sort = ? WHERE id = ?", [(i, pid) for i, pid in enumerate(order)])
    return _redirect(f"/host/listings/{listing_id}/edit#photos")


@router.post("/host/listings/{listing_id}/blocks")
def add_block(request: Request, listing_id: int, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user),
              start_at: str = Form(...), end_at: str = Form(...), reason: str = Form("")):
    if (g := _host_guard(request, u)):
        return g
    if _own_listing(conn, u, listing_id) and len(start_at) == 16 and len(end_at) == 16 and start_at < end_at:
        conn.execute("INSERT INTO availability_blocks (listing_id, start_at, end_at, reason) VALUES (?,?,?,?)",
                     (listing_id, start_at, end_at, reason.strip()[:200]))
    return _redirect(f"/host/listings/{listing_id}/edit#blocks")


@router.post("/host/listings/{listing_id}/blocks/{block_id}/delete")
def delete_block(request: Request, listing_id: int, block_id: int, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user)):
    if (g := _host_guard(request, u)):
        return g
    if _own_listing(conn, u, listing_id):
        conn.execute("DELETE FROM availability_blocks WHERE id = ? AND listing_id = ?", (block_id, listing_id))
    return _redirect(f"/host/listings/{listing_id}/edit#blocks")


@router.get("/host/listings/{listing_id}/calendar", response_class=HTMLResponse)
def host_calendar(request: Request, listing_id: int, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user), month: str = ""):
    """Month view: per-day occupancy, price, bookings and blocks, plus pricing-rule and block management."""
    if (g := _host_guard(request, u)):
        return g
    l = _own_listing(conn, u, listing_id)
    if not l:
        return render(request, "error.html", {"user": u, "message": "Listing not found."}, 404)
    now = local_now(l["timezone"])
    try:
        first = datetime.strptime(month + "-01", "%Y-%m-%d").date() if month else now.date().replace(day=1)
    except ValueError:
        first = now.date().replace(day=1)
    # grid starts on the Monday on/before the 1st and covers 6 weeks
    grid_start = first - timedelta(days=first.weekday())
    n_days = 42
    busy = busy_ranges(conn, l, grid_start, n_days, datetime.min)
    summary = free_hours_by_day(busy, grid_start, n_days)
    g0 = datetime.combine(grid_start, datetime.min.time())
    rules = rules_for(conn, l["id"], g0, g0 + timedelta(days=n_days))
    d0, d1 = grid_start.isoformat() + "T00:00", (grid_start + timedelta(days=n_days)).isoformat() + "T00:00"
    bks = rows(conn, """SELECT b.*, u.name AS guest_name FROM bookings b JOIN users u ON u.id = b.guest_id
                        WHERE b.listing_id = ? AND b.status IN ('awaiting_payment','pending','confirmed','completed')
                        AND b.start_at < ? AND b.end_at > ? ORDER BY b.start_at""", (listing_id, d1, d0))
    blocks = rows(conn, "SELECT * FROM availability_blocks WHERE listing_id = ? AND start_at < ? AND end_at > ? ORDER BY start_at", (listing_id, d1, d0))
    days = []
    for i in range(n_days):
        d = grid_start + timedelta(days=i)
        ds, de = d.isoformat() + "T00:00", (d + timedelta(days=1)).isoformat() + "T00:00"
        days.append({
            "date": d, "in_month": d.month == first.month, "is_today": d == now.date(), "past": d < now.date(),
            "free_hours": summary[i]["free_hours"], "state": summary[i]["state"],
            "rate": day_rate(l, rules, datetime.combine(d, datetime.min.time())),
            "bookings": [b for b in bks if b["start_at"] < de and b["end_at"] > ds],
            "blocks": [b for b in blocks if b["start_at"] < de and b["end_at"] > ds],
        })
    all_rules = rows(conn, "SELECT * FROM price_rules WHERE listing_id = ? AND end_date >= ? ORDER BY start_date, id", (listing_id, now.strftime("%Y-%m-%d")))
    upcoming_blocks = rows(conn, "SELECT * FROM availability_blocks WHERE listing_id = ? AND end_at >= ? ORDER BY start_at", (listing_id, now.strftime("%Y-%m-%dT%H:%M")))
    prev_month = (first - timedelta(days=1)).replace(day=1)
    next_month = (first + timedelta(days=32)).replace(day=1)
    return render(request, "host/calendar.html", {
        "user": u, "l": l, "days": days, "first": first, "prev_month": prev_month.strftime("%Y-%m"), "next_month": next_month.strftime("%Y-%m"),
        "rules": all_rules, "blocks": upcoming_blocks, "hours": list(range(25)),
    })


@router.post("/host/listings/{listing_id}/price-rules")
async def add_price_rule(request: Request, listing_id: int, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user)):
    if (g := _host_guard(request, u)):
        return g
    if not _own_listing(conn, u, listing_id):
        return render(request, "error.html", {"user": u, "message": "Listing not found."}, 404)
    form = await request.form()
    start_date, end_date = (form.get("start_date") or "").strip(), (form.get("end_date") or "").strip()
    hourly_rate, daily_rate, label = form.get("hourly_rate") or "0", (form.get("daily_rate") or "").strip(), form.get("label") or ""
    weekdays = "".join(sorted(set(d for d in form.getlist("weekday") if d in "0123456"))) or "0123456"
    try:
        hour_from, hour_until = int(form.get("hour_from") or 0), int(form.get("hour_until") or 24)
        date.fromisoformat(start_date), date.fromisoformat(end_date)
        hourly = int(round(float(hourly_rate) * 100))
        daily = int(round(float(daily_rate) * 100)) if daily_rate else 0
    except ValueError:
        return _redirect(f"/host/listings/{listing_id}/calendar?month={start_date[:7]}&err=1")
    if end_date < start_date or hourly <= 0 or not (0 <= hour_from < hour_until <= 24):
        return _redirect(f"/host/listings/{listing_id}/calendar?month={start_date[:7]}&err=1")
    conn.execute("""INSERT INTO price_rules (listing_id, label, start_date, end_date, weekdays, hour_from, hour_until, hourly_rate_cents, daily_rate_cents)
                    VALUES (?,?,?,?,?,?,?,?,?)""", (listing_id, label.strip()[:60], start_date, end_date, weekdays, hour_from, hour_until, hourly, daily))
    return _redirect(f"/host/listings/{listing_id}/calendar?month={start_date[:7]}#rules")


@router.post("/host/listings/{listing_id}/price-rules/{rule_id}/delete")
def delete_price_rule(request: Request, listing_id: int, rule_id: int, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user)):
    if (g := _host_guard(request, u)):
        return g
    if _own_listing(conn, u, listing_id):
        conn.execute("DELETE FROM price_rules WHERE id = ? AND listing_id = ?", (rule_id, listing_id))
    return _redirect(f"/host/listings/{listing_id}/calendar#rules")


# ---------------------------------------------------------------- payouts (Stripe Connect Express)


def _payout_ctx(conn, u, error=None):
    acct = row(conn, "SELECT stripe_account_id, stripe_payouts_enabled FROM users WHERE id = ?", (u["id"],))
    status = None
    if acct["stripe_account_id"] and payments.configured():
        try:
            status = payments.account_status(acct["stripe_account_id"])
            conn.execute("UPDATE users SET stripe_payouts_enabled = ? WHERE id = ?", (1 if status["payouts_enabled"] else 0, u["id"]))
            acct = dict(acct, stripe_payouts_enabled=1 if status["payouts_enabled"] else 0)
        except payments.PaymentError as e:
            error = error or str(e)
    payouts = host_payouts(conn, None if u.get("is_admin") else u["id"])
    total = sum(p["host_payout_cents"] for p in payouts)
    return {"user": u, "acct": acct, "status": status, "payouts": payouts, "total_cents": total, "stripe": payments.configured(), "error": error,
            "all_hosts": bool(u.get("is_admin"))}


@router.get("/host/payouts", response_class=HTMLResponse)
def payouts_page(request: Request, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user), connected: int = 0):
    if (g := _host_guard(request, u)):
        return g
    ctx = _payout_ctx(conn, u)
    ctx["just_returned"] = bool(connected)
    return render(request, "host/payouts.html", ctx)


@router.post("/host/payouts/connect")
def payouts_connect(request: Request, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user)):
    """Create the host's Express account if needed and send them to Stripe's hosted onboarding."""
    if (g := _host_guard(request, u)):
        return g
    if not payments.configured():
        return render(request, "host/payouts.html", _payout_ctx(conn, u, "Stripe is not configured on this server yet."), 400)
    acct = row(conn, "SELECT stripe_account_id FROM users WHERE id = ?", (u["id"],))
    try:
        account_id = acct["stripe_account_id"]
        if not account_id:
            account_id = payments.create_connect_account(u["email"], u["name"])
            conn.execute("UPDATE users SET stripe_account_id = ? WHERE id = ?", (account_id, u["id"]))
        url = payments.account_onboarding_link(account_id, f"{settings.BASE_URL}/host/payouts/refresh", f"{settings.BASE_URL}/host/payouts?connected=1")
    except payments.PaymentError as e:
        return render(request, "host/payouts.html", _payout_ctx(conn, u, str(e)), 502)
    return _redirect(url)


@router.get("/host/payouts/refresh")
def payouts_refresh(request: Request, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user)):
    """Stripe sends the host here when an onboarding link expired: issue a fresh one."""
    if (g := _host_guard(request, u)):
        return g
    acct = row(conn, "SELECT stripe_account_id FROM users WHERE id = ?", (u["id"],))
    if not acct["stripe_account_id"] or not payments.configured():
        return _redirect("/host/payouts")
    try:
        return _redirect(payments.account_onboarding_link(acct["stripe_account_id"], f"{settings.BASE_URL}/host/payouts/refresh", f"{settings.BASE_URL}/host/payouts?connected=1"))
    except payments.PaymentError as e:
        return render(request, "host/payouts.html", _payout_ctx(conn, u, str(e)), 502)


@router.post("/host/payouts/dashboard")
def payouts_dashboard(request: Request, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user)):
    if (g := _host_guard(request, u)):
        return g
    acct = row(conn, "SELECT stripe_account_id FROM users WHERE id = ?", (u["id"],))
    if not acct["stripe_account_id"] or not payments.configured():
        return _redirect("/host/payouts")
    try:
        return _redirect(payments.express_dashboard_link(acct["stripe_account_id"]))
    except payments.PaymentError as e:
        return render(request, "host/payouts.html", _payout_ctx(conn, u, str(e)), 502)


@router.post("/admin/bookings/{booking_id}/paid-manually")
def admin_mark_paid(request: Request, booking_id: int, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user)):
    if (g := _admin_guard(request, u)):
        return g
    conn.execute("UPDATE bookings SET payout_status = 'paid_manually' WHERE id = ? AND payout_status = 'pending'", (booking_id,))
    return _redirect("/host/payouts")


# ---------------------------------------------------------------- admin


def _admin_guard(request: Request, u: dict | None):
    if not u:
        return _login_redirect(request)
    if not u["is_admin"]:
        return render(request, "error.html", {"user": u, "message": "Admin access required."}, 403)
    return None


@router.get("/admin", response_class=HTMLResponse)
def admin_home(request: Request, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user), tab: str = "overview", q: str = ""):
    if (g := _admin_guard(request, u)):
        return g
    ctx = {"user": u, "tab": tab, "q": q, "overview": admin_overview(conn)}
    like = f"%{q}%"
    if tab == "users":
        ctx["users"] = rows(conn, "SELECT * FROM users WHERE name LIKE ? OR email LIKE ? ORDER BY id DESC LIMIT 200", (like, like))
    elif tab == "payouts":
        return _redirect("/host/payouts")
    elif tab == "listings":
        ctx["listings"] = rows(conn, LISTING_CARD_SQL + " WHERE l.title LIKE ? OR l.city LIKE ? ORDER BY l.id DESC LIMIT 200", (like, like))
    elif tab == "bookings":
        ctx["bookings"] = rows(conn, """SELECT b.*, l.title AS listing_title, g.name AS guest_name, h.name AS host_name FROM bookings b
                                        JOIN listings l ON l.id = b.listing_id JOIN users g ON g.id = b.guest_id JOIN users h ON h.id = l.host_id
                                        WHERE l.title LIKE ? OR g.email LIKE ? OR h.email LIKE ? ORDER BY b.id DESC LIMIT 200""", (like, like, like))
    return render(request, "admin.html", ctx)


@router.post("/admin/users/{user_id}/ban")
def admin_ban(request: Request, user_id: int, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user), banned: int = Form(1)):
    if (g := _admin_guard(request, u)):
        return g
    if user_id != u["id"]:
        conn.execute("UPDATE users SET is_banned = ? WHERE id = ?", (1 if banned else 0, user_id))
        if banned:
            conn.execute("UPDATE listings SET status = 'paused' WHERE host_id = ?", (user_id,))
    return _redirect("/admin?tab=users")


@router.post("/admin/listings/{listing_id}/status")
def admin_listing_status(request: Request, listing_id: int, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user), status: str = Form(...)):
    if (g := _admin_guard(request, u)):
        return g
    if status in ("active", "paused"):
        conn.execute("UPDATE listings SET status = ? WHERE id = ?", (status, listing_id))
    return _redirect("/admin?tab=listings")


@router.post("/admin/bookings/{booking_id}/cancel")
def admin_cancel_booking(request: Request, booking_id: int, conn: sqlite3.Connection = Depends(db), u: dict | None = Depends(user)):
    if (g := _admin_guard(request, u)):
        return g
    b = booking_svc.get_booking(conn, booking_id)
    if b:
        try:
            booking_svc.cancel(conn, booking_id, b["host_id"])  # acts as the host: full refund
        except booking_svc.BookingError as e:
            return render(request, "error.html", {"user": u, "message": str(e)}, 409)
    return _redirect("/admin?tab=bookings")
