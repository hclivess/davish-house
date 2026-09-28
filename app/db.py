"""SQLite access layer: connection helper, schema, and small query utilities.

All timestamps are stored as naive ISO strings in the listing's local time,
formatted "YYYY-MM-DDTHH:MM". They compare correctly as strings.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from . import settings

DB_PATH = settings.DB_PATH

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    name          TEXT NOT NULL,
    is_host       INTEGER NOT NULL DEFAULT 0,
    is_admin      INTEGER NOT NULL DEFAULT 0,
    is_banned     INTEGER NOT NULL DEFAULT 0,
    bio           TEXT NOT NULL DEFAULT '',
    phone         TEXT NOT NULL DEFAULT '',
    avatar_url    TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M', 'now'))
);

CREATE TABLE IF NOT EXISTS listings (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    host_id            INTEGER NOT NULL REFERENCES users(id),
    title              TEXT NOT NULL,
    description        TEXT NOT NULL DEFAULT '',
    category           TEXT NOT NULL DEFAULT 'apartment',
    bedrooms           INTEGER NOT NULL DEFAULT 1,   -- 0 = studio
    bathrooms          REAL NOT NULL DEFAULT 1,
    beds               INTEGER NOT NULL DEFAULT 1,
    city               TEXT NOT NULL,
    neighborhood       TEXT NOT NULL DEFAULT '',
    address            TEXT NOT NULL DEFAULT '',
    lat                REAL,
    lng                REAL,
    capacity           INTEGER NOT NULL DEFAULT 1,
    hourly_rate_cents  INTEGER NOT NULL,
    cleaning_fee_cents INTEGER NOT NULL DEFAULT 0,
    min_hours          REAL NOT NULL DEFAULT 1,
    max_hours          REAL NOT NULL DEFAULT 720,
    daily_rate_cents   INTEGER NOT NULL DEFAULT 0,      -- optional discounted 24h rate
    checkin_from       TEXT NOT NULL DEFAULT '00:00',
    checkin_until      TEXT NOT NULL DEFAULT '24:00',
    checkout_from      TEXT NOT NULL DEFAULT '00:00',
    checkout_until     TEXT NOT NULL DEFAULT '24:00',
    size_m2            INTEGER,
    floor              TEXT NOT NULL DEFAULT '',
    house_rules        TEXT NOT NULL DEFAULT '',
    checkin_instructions TEXT NOT NULL DEFAULT '',   -- private: shown to confirmed guests only
    advance_notice_hours INTEGER NOT NULL DEFAULT 2, -- earliest check-in is now + this
    max_advance_days   INTEGER NOT NULL DEFAULT 365, -- booking window
    cancellation_policy TEXT NOT NULL DEFAULT 'flexible',  -- flexible | moderate | strict
    weekend_hourly_rate_cents INTEGER NOT NULL DEFAULT 0,  -- Fri + Sat hours, 0 = same as base
    long_stay_discount_pct INTEGER NOT NULL DEFAULT 0,     -- stays of 7+ days
    monthly_rate_cents INTEGER NOT NULL DEFAULT 0,         -- cap per 30 days, 0 = none
    included_guests    INTEGER NOT NULL DEFAULT 0,         -- guests included in the price (0 = all)
    extra_guest_fee_cents INTEGER NOT NULL DEFAULT 0,      -- per extra guest, per day (or per stay under 24h)
    buffer_minutes     INTEGER NOT NULL DEFAULT 30,
    instant_book       INTEGER NOT NULL DEFAULT 1,
    timezone           TEXT NOT NULL DEFAULT 'UTC',
    status             TEXT NOT NULL DEFAULT 'active',   -- active | paused
    created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_listings_city ON listings(city);

CREATE TABLE IF NOT EXISTS listing_photos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    url        TEXT NOT NULL,       -- /uploads/<listing>/<file>.jpg for uploads, or an external URL
    sort       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_photos_listing ON listing_photos(listing_id, sort);

CREATE TABLE IF NOT EXISTS listing_amenities (
    listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    amenity    TEXT NOT NULL,
    PRIMARY KEY (listing_id, amenity)
);

-- Legacy (unused since the move to continuous availability); kept so old databases open cleanly.
CREATE TABLE IF NOT EXISTS availability_rules (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    weekday    INTEGER NOT NULL,
    open_time  TEXT NOT NULL,   -- 'HH:MM'
    close_time TEXT NOT NULL    -- 'HH:MM', '24:00' allowed
);
CREATE INDEX IF NOT EXISTS idx_rules_listing ON availability_rules(listing_id);

-- Calendar pricing: overrides for a date range, optionally limited to weekdays and hours of the day.
-- The most recently created matching rule wins for a given hour.
CREATE TABLE IF NOT EXISTS price_rules (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id        INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    label             TEXT NOT NULL DEFAULT '',
    start_date        TEXT NOT NULL,    -- YYYY-MM-DD inclusive
    end_date          TEXT NOT NULL,    -- YYYY-MM-DD inclusive
    weekdays          TEXT NOT NULL DEFAULT '0123456',  -- digits of weekdays the rule applies to (0=Mon)
    hour_from         INTEGER NOT NULL DEFAULT 0,       -- 0-23 inclusive
    hour_until        INTEGER NOT NULL DEFAULT 24,      -- exclusive, 24 = end of day
    hourly_rate_cents INTEGER NOT NULL,
    daily_rate_cents  INTEGER NOT NULL DEFAULT 0,       -- 0 = keep listing's daily rate
    created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_price_rules_listing ON price_rules(listing_id, start_date);

CREATE TABLE IF NOT EXISTS favorites (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M', 'now')),
    PRIMARY KEY (user_id, listing_id)
);

-- Host-defined blocked periods (maintenance, private use, ...).
CREATE TABLE IF NOT EXISTS availability_blocks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    start_at   TEXT NOT NULL,
    end_at     TEXT NOT NULL,
    reason     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_blocks_listing ON availability_blocks(listing_id, start_at);

CREATE TABLE IF NOT EXISTS bookings (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id         INTEGER NOT NULL REFERENCES listings(id),
    guest_id           INTEGER NOT NULL REFERENCES users(id),
    start_at           TEXT NOT NULL,
    end_at             TEXT NOT NULL,
    guests             INTEGER NOT NULL DEFAULT 1,
    hours              REAL NOT NULL,
    subtotal_cents     INTEGER NOT NULL,
    cleaning_fee_cents INTEGER NOT NULL,
    service_fee_cents  INTEGER NOT NULL,
    total_cents        INTEGER NOT NULL,
    host_payout_cents  INTEGER NOT NULL,
    status             TEXT NOT NULL,  -- pending | confirmed | declined | cancelled | completed
    payment_status     TEXT NOT NULL DEFAULT 'unpaid',  -- unpaid | authorized | paid | refunded | disputed
    note               TEXT NOT NULL DEFAULT '',
    expires_at         TEXT,            -- UTC; awaiting_payment bookings are released after this
    stripe_session_id  TEXT,
    stripe_payment_intent TEXT,
    refund_cents       INTEGER NOT NULL DEFAULT 0,
    extra_guest_cents  INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_bookings_listing_time ON bookings(listing_id, start_at, end_at);
CREATE INDEX IF NOT EXISTS idx_bookings_guest ON bookings(guest_id);

CREATE TABLE IF NOT EXISTS reviews (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER NOT NULL UNIQUE REFERENCES bookings(id),
    listing_id INTEGER NOT NULL REFERENCES listings(id),
    author_id  INTEGER NOT NULL REFERENCES users(id),
    rating     INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    cleanliness   INTEGER, accuracy INTEGER, communication INTEGER, location INTEGER, value INTEGER,
    body       TEXT NOT NULL DEFAULT '',
    host_reply TEXT NOT NULL DEFAULT '',
    host_reply_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M', 'now'))
);

-- Hosts review guests after a completed stay (visible to other hosts on the guest's profile).
CREATE TABLE IF NOT EXISTS guest_reviews (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER NOT NULL UNIQUE REFERENCES bookings(id),
    guest_id   INTEGER NOT NULL REFERENCES users(id),
    host_id    INTEGER NOT NULL REFERENCES users(id),
    rating     INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    body       TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M', 'now'))
);

CREATE TABLE IF NOT EXISTS password_resets (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL,
    used       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    sender_id  INTEGER NOT NULL REFERENCES users(id),
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M', 'now'))
);
"""


def connect(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or DB_PATH, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


MIGRATIONS = [
    ("listings", "timezone", "ALTER TABLE listings ADD COLUMN timezone TEXT NOT NULL DEFAULT 'UTC'"),
    ("listings", "bedrooms", "ALTER TABLE listings ADD COLUMN bedrooms INTEGER NOT NULL DEFAULT 1"),
    ("listings", "bathrooms", "ALTER TABLE listings ADD COLUMN bathrooms REAL NOT NULL DEFAULT 1"),
    ("listings", "beds", "ALTER TABLE listings ADD COLUMN beds INTEGER NOT NULL DEFAULT 1"),
    ("listings", "daily_rate_cents", "ALTER TABLE listings ADD COLUMN daily_rate_cents INTEGER NOT NULL DEFAULT 0"),
    ("listings", "checkin_from", "ALTER TABLE listings ADD COLUMN checkin_from TEXT NOT NULL DEFAULT '00:00'"),
    ("listings", "checkin_until", "ALTER TABLE listings ADD COLUMN checkin_until TEXT NOT NULL DEFAULT '24:00'"),
    ("listings", "checkout_from", "ALTER TABLE listings ADD COLUMN checkout_from TEXT NOT NULL DEFAULT '00:00'"),
    ("listings", "checkout_until", "ALTER TABLE listings ADD COLUMN checkout_until TEXT NOT NULL DEFAULT '24:00'"),
    ("listings", "size_m2", "ALTER TABLE listings ADD COLUMN size_m2 INTEGER"),
    ("listings", "floor", "ALTER TABLE listings ADD COLUMN floor TEXT NOT NULL DEFAULT ''"),
    ("listings", "house_rules", "ALTER TABLE listings ADD COLUMN house_rules TEXT NOT NULL DEFAULT ''"),
    ("listings", "checkin_instructions", "ALTER TABLE listings ADD COLUMN checkin_instructions TEXT NOT NULL DEFAULT ''"),
    ("listings", "advance_notice_hours", "ALTER TABLE listings ADD COLUMN advance_notice_hours INTEGER NOT NULL DEFAULT 2"),
    ("listings", "max_advance_days", "ALTER TABLE listings ADD COLUMN max_advance_days INTEGER NOT NULL DEFAULT 365"),
    ("listings", "cancellation_policy", "ALTER TABLE listings ADD COLUMN cancellation_policy TEXT NOT NULL DEFAULT 'flexible'"),
    ("listings", "weekend_hourly_rate_cents", "ALTER TABLE listings ADD COLUMN weekend_hourly_rate_cents INTEGER NOT NULL DEFAULT 0"),
    ("listings", "long_stay_discount_pct", "ALTER TABLE listings ADD COLUMN long_stay_discount_pct INTEGER NOT NULL DEFAULT 0"),
    ("listings", "monthly_rate_cents", "ALTER TABLE listings ADD COLUMN monthly_rate_cents INTEGER NOT NULL DEFAULT 0"),
    ("listings", "included_guests", "ALTER TABLE listings ADD COLUMN included_guests INTEGER NOT NULL DEFAULT 0"),
    ("listings", "extra_guest_fee_cents", "ALTER TABLE listings ADD COLUMN extra_guest_fee_cents INTEGER NOT NULL DEFAULT 0"),
    ("bookings", "extra_guest_cents", "ALTER TABLE bookings ADD COLUMN extra_guest_cents INTEGER NOT NULL DEFAULT 0"),
    ("users", "is_admin", "ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0"),
    ("users", "is_banned", "ALTER TABLE users ADD COLUMN is_banned INTEGER NOT NULL DEFAULT 0"),
    ("users", "bio", "ALTER TABLE users ADD COLUMN bio TEXT NOT NULL DEFAULT ''"),
    ("users", "phone", "ALTER TABLE users ADD COLUMN phone TEXT NOT NULL DEFAULT ''"),
    ("users", "avatar_url", "ALTER TABLE users ADD COLUMN avatar_url TEXT NOT NULL DEFAULT ''"),
    ("reviews", "cleanliness", "ALTER TABLE reviews ADD COLUMN cleanliness INTEGER"),
    ("reviews", "accuracy", "ALTER TABLE reviews ADD COLUMN accuracy INTEGER"),
    ("reviews", "communication", "ALTER TABLE reviews ADD COLUMN communication INTEGER"),
    ("reviews", "location", "ALTER TABLE reviews ADD COLUMN location INTEGER"),
    ("reviews", "value", "ALTER TABLE reviews ADD COLUMN value INTEGER"),
    ("reviews", "host_reply", "ALTER TABLE reviews ADD COLUMN host_reply TEXT NOT NULL DEFAULT ''"),
    ("reviews", "host_reply_at", "ALTER TABLE reviews ADD COLUMN host_reply_at TEXT"),
    ("bookings", "expires_at", "ALTER TABLE bookings ADD COLUMN expires_at TEXT"),
    ("bookings", "stripe_session_id", "ALTER TABLE bookings ADD COLUMN stripe_session_id TEXT"),
    ("bookings", "stripe_payment_intent", "ALTER TABLE bookings ADD COLUMN stripe_payment_intent TEXT"),
    ("bookings", "refund_cents", "ALTER TABLE bookings ADD COLUMN refund_cents INTEGER NOT NULL DEFAULT 0"),
    ("users", "email_verified", "ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0"),
]


def init_db(path: str | None = None) -> None:
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
        for table, column, ddl in MIGRATIONS:
            cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            if column not in cols:
                conn.execute(ddl)
    finally:
        conn.close()


@contextmanager
def get_db(path: str | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """BEGIN IMMEDIATE so concurrent booking attempts serialize on the write lock."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def rows(conn: sqlite3.Connection, sql: str, params=()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def row(conn: sqlite3.Connection, sql: str, params=()) -> dict | None:
    r = conn.execute(sql, params).fetchone()
    return dict(r) if r else None
