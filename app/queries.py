"""Read-side queries shared by pages and the API."""
from __future__ import annotations

import sqlite3
from datetime import datetime

from .availability import listing_is_free
from .db import row, rows

LISTING_CARD_SQL = """
SELECT l.*, u.name AS host_name,
       (SELECT url FROM listing_photos p WHERE p.listing_id = l.id ORDER BY sort LIMIT 1) AS cover_url,
       (SELECT ROUND(AVG(rating), 2) FROM reviews r WHERE r.listing_id = l.id) AS avg_rating,
       (SELECT COUNT(*) FROM reviews r WHERE r.listing_id = l.id) AS review_count
FROM listings l JOIN users u ON u.id = l.host_id
"""


def search_listings(
    conn: sqlite3.Connection, *, city: str = "", bedrooms: int = -1, capacity: int = 0,
    max_rate_cents: int = 0, min_rate_cents: int = 0, checkin: str = "", checkout: str = "", now: datetime | None = None,
    amenities: list[str] | None = None, instant_only: bool = False, sort: str = "recommended", user_id: int | None = None,
    limit: int = 60,
) -> list[dict]:
    where = ["l.status = 'active'"]
    params: list = []
    if instant_only:
        where.append("l.instant_book = 1")
    for a in amenities or []:
        where.append("EXISTS (SELECT 1 FROM listing_amenities la WHERE la.listing_id = l.id AND la.amenity = ?)")
        params.append(a)
    if min_rate_cents:
        where.append("l.hourly_rate_cents >= ?")
        params.append(min_rate_cents)
    if city:
        where.append("(l.city LIKE ? OR l.neighborhood LIKE ?)")
        params += [f"%{city}%", f"%{city}%"]
    if bedrooms >= 3:
        where.append("l.bedrooms >= 3")
    elif bedrooms >= 0:
        where.append("l.bedrooms = ?")
        params.append(bedrooms)
    if capacity:
        where.append("l.capacity >= ?")
        params.append(capacity)
    if max_rate_cents:
        where.append("l.hourly_rate_cents <= ?")
        params.append(max_rate_cents)
    order = {"price_asc": "l.hourly_rate_cents ASC, l.id", "price_desc": "l.hourly_rate_cents DESC, l.id",
             "rating": "avg_rating DESC NULLS LAST, review_count DESC, l.id", "newest": "l.id DESC"}.get(sort, "review_count DESC, avg_rating DESC, l.id")
    sql = LISTING_CARD_SQL + " WHERE " + " AND ".join(where) + f" ORDER BY {order} LIMIT ?"
    params.append(limit)
    results = rows(conn, sql, params)
    if checkin and checkout:
        results = [l for l in results if listing_is_free(conn, l, checkin, checkout, now)]
    if user_id:
        favs = {r["listing_id"] for r in rows(conn, "SELECT listing_id FROM favorites WHERE user_id = ?", (user_id,))}
        for l in results:
            l["is_favorite"] = l["id"] in favs
    return results


def user_favorites(conn: sqlite3.Connection, user_id: int) -> list[dict]:
    out = rows(conn, LISTING_CARD_SQL + " JOIN favorites f ON f.listing_id = l.id AND f.user_id = ? WHERE l.status = 'active' ORDER BY f.created_at DESC", (user_id,))
    for l in out:
        l["is_favorite"] = True
    return out


def public_profile(conn: sqlite3.Connection, user_id: int) -> dict | None:
    u = row(conn, "SELECT id, name, bio, avatar_url, is_host, created_at FROM users WHERE id = ? AND is_banned = 0 AND password_hash != 'deleted'", (user_id,))
    if not u:
        return None
    u["listings"] = rows(conn, LISTING_CARD_SQL + " WHERE l.host_id = ? AND l.status = 'active' ORDER BY review_count DESC", (user_id,))
    u["reviews_received"] = rows(conn, """SELECT r.*, a.name AS author_name, l.title AS listing_title FROM reviews r
                                          JOIN listings l ON l.id = r.listing_id JOIN users a ON a.id = r.author_id
                                          WHERE l.host_id = ? ORDER BY r.created_at DESC LIMIT 30""", (user_id,))
    u["guest_reviews"] = rows(conn, """SELECT gr.*, h.name AS host_name FROM guest_reviews gr JOIN users h ON h.id = gr.host_id
                                       WHERE gr.guest_id = ? ORDER BY gr.created_at DESC LIMIT 30""", (user_id,))
    stats = row(conn, """SELECT COUNT(*) AS n, ROUND(AVG(r.rating), 2) AS avg FROM reviews r JOIN listings l ON l.id = r.listing_id WHERE l.host_id = ?""", (user_id,))
    u["host_review_count"], u["host_avg_rating"] = stats["n"], stats["avg"]
    return u


def host_payouts(conn: sqlite3.Connection, host_id: int | None) -> list[dict]:
    """Confirmed/completed bookings with their payout amount and route (for a host, or all hosts when None)."""
    return rows(conn, """SELECT b.id, b.start_at, b.end_at, b.host_payout_cents, b.total_cents, b.status, b.payment_status, b.payout_status,
                                b.stripe_destination, l.title AS listing_title, l.host_id, h.name AS host_name, g.name AS guest_name
                         FROM bookings b JOIN listings l ON l.id = b.listing_id JOIN users h ON h.id = l.host_id JOIN users g ON g.id = b.guest_id
                         WHERE b.status IN ('confirmed','completed') AND (? IS NULL OR l.host_id = ?) ORDER BY b.start_at DESC LIMIT 300""",
                (host_id, host_id))


def admin_overview(conn: sqlite3.Connection) -> dict:
    return {
        "users": row(conn, "SELECT COUNT(*) AS n, SUM(is_host) AS hosts, SUM(is_banned) AS banned FROM users"),
        "listings": row(conn, "SELECT COUNT(*) AS n, SUM(status = 'active') AS active FROM listings"),
        "bookings": row(conn, """SELECT COUNT(*) AS n, SUM(status = 'confirmed') AS confirmed, SUM(status = 'pending') AS pending,
                                 COALESCE(SUM(CASE WHEN status IN ('confirmed','completed') THEN total_cents END), 0) AS gross_cents,
                                 COALESCE(SUM(CASE WHEN status IN ('confirmed','completed') THEN total_cents - host_payout_cents END), 0) AS platform_cents
                                 FROM bookings"""),
    }


def listing_detail(conn: sqlite3.Connection, listing_id: int) -> dict | None:
    l = row(conn, LISTING_CARD_SQL + " WHERE l.id = ?", (listing_id,))
    if not l:
        return None
    l["photo_rows"] = rows(conn, "SELECT id, url, sort FROM listing_photos WHERE listing_id = ? ORDER BY sort, id", (listing_id,))
    l["photos"] = [p["url"] for p in l["photo_rows"]]
    l["amenities"] = [a["amenity"] for a in rows(conn, "SELECT amenity FROM listing_amenities WHERE listing_id = ? ORDER BY amenity", (listing_id,))]
    l["reviews"] = rows(
        conn,
        "SELECT r.*, u.name AS author_name, u.avatar_url AS author_avatar FROM reviews r JOIN users u ON u.id = r.author_id WHERE r.listing_id = ? ORDER BY r.created_at DESC LIMIT 30",
        (listing_id,),
    )
    l["category_ratings"] = row(conn, """SELECT ROUND(AVG(cleanliness),1) AS cleanliness, ROUND(AVG(accuracy),1) AS accuracy, ROUND(AVG(communication),1) AS communication,
                                         ROUND(AVG(location),1) AS location, ROUND(AVG(value),1) AS value FROM reviews WHERE listing_id = ?""", (listing_id,))
    l["price_rules"] = rows(conn, "SELECT * FROM price_rules WHERE listing_id = ? AND end_date >= date('now') ORDER BY start_date", (listing_id,))
    host = row(conn, "SELECT avatar_url, bio, created_at FROM users WHERE id = ?", (l["host_id"],))
    l["host_avatar"], l["host_bio"], l["host_since"] = host["avatar_url"], host["bio"], host["created_at"]
    return l


def booking_detail(conn: sqlite3.Connection, booking_id: int) -> dict | None:
    b = row(
        conn,
        """SELECT b.*, l.title AS listing_title, l.city, l.address, l.host_id, l.bedrooms, l.instant_book, l.checkin_instructions, l.house_rules,
                  l.cancellation_policy, l.timezone,
                  u.name AS guest_name, h.name AS host_name,
                  (SELECT url FROM listing_photos p WHERE p.listing_id = l.id ORDER BY sort LIMIT 1) AS cover_url,
                  (SELECT id FROM reviews r WHERE r.booking_id = b.id) AS review_id,
                  (SELECT id FROM guest_reviews gr WHERE gr.booking_id = b.id) AS guest_review_id
           FROM bookings b JOIN listings l ON l.id = b.listing_id
           JOIN users u ON u.id = b.guest_id JOIN users h ON h.id = l.host_id WHERE b.id = ?""",
        (booking_id,),
    )
    if b:
        b["messages"] = rows(
            conn,
            "SELECT m.*, u.name AS sender_name FROM messages m JOIN users u ON u.id = m.sender_id WHERE booking_id = ? ORDER BY m.id",
            (booking_id,),
        )
    return b


def user_trips(conn: sqlite3.Connection, user_id: int) -> list[dict]:
    return rows(
        conn,
        """SELECT b.*, l.title AS listing_title, l.city, l.bedrooms,
                  (SELECT url FROM listing_photos p WHERE p.listing_id = l.id ORDER BY sort LIMIT 1) AS cover_url,
                  (SELECT id FROM reviews r WHERE r.booking_id = b.id) AS review_id
           FROM bookings b JOIN listings l ON l.id = b.listing_id WHERE b.guest_id = ? ORDER BY b.start_at DESC""",
        (user_id,),
    )


def host_bookings(conn: sqlite3.Connection, host_id: int | None, status: str | None = None) -> list[dict]:
    """Bookings for one host, or for every host when host_id is None (admin)."""
    sql = """SELECT b.*, l.title AS listing_title, u.name AS guest_name
             FROM bookings b JOIN listings l ON l.id = b.listing_id JOIN users u ON u.id = b.guest_id
             WHERE (? IS NULL OR l.host_id = ?)"""
    params: list = [host_id, host_id]
    if status:
        sql += " AND b.status = ?"
        params.append(status)
    sql += " ORDER BY CASE b.status WHEN 'pending' THEN 0 ELSE 1 END, b.start_at DESC"
    return rows(conn, sql, params)


def host_stats(conn: sqlite3.Connection, host_id: int | None) -> dict:
    return row(
        conn,
        """SELECT COUNT(*) AS bookings,
                  COALESCE(SUM(CASE WHEN b.status IN ('confirmed','completed') THEN b.host_payout_cents END), 0) AS earnings_cents,
                  COALESCE(SUM(CASE WHEN b.status = 'awaiting_payment' THEN 1 ELSE 0 END), 0) AS awaiting,
                  COALESCE(SUM(CASE WHEN b.status IN ('confirmed','completed') THEN b.hours END), 0) AS hours_booked,
                  SUM(CASE WHEN b.status = 'pending' THEN 1 ELSE 0 END) AS pending
           FROM bookings b JOIN listings l ON l.id = b.listing_id WHERE (? IS NULL OR l.host_id = ?)""",
        (host_id, host_id),
    ) or {}
