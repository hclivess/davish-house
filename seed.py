"""Populate the database with demo hosts, listings, opening hours, bookings and reviews.

    python seed.py            # seed (skips if data exists)
    python seed.py --reset    # wipe and reseed
"""
from __future__ import annotations

import os
import random
import sys
from datetime import date, datetime, timedelta

from app.auth import hash_password
from app.bookings import create_booking
from app.db import DB_PATH, connect, init_db

random.seed(7)
PASSWORD = "password123"

HOSTS = [("host@example.com", "Maya Chen"), ("sam@example.com", "Sam Okafor"), ("lena@example.com", "Lena Rossi")]
GUESTS = [("guest@example.com", "Alex Guest"), ("jordan@example.com", "Jordan Park"), ("priya@example.com", "Priya Nair"),
          ("tom@example.com", "Tom Brandt")]

# (title, bedrooms, bathrooms, beds, city, neighborhood, guests, rate, cleaning, min_h, max_h, buffer, instant, amenities, description)
LISTINGS = [
    ("Sunlit loft in Williamsburg", 1, 1, 1, "New York", "Williamsburg", 4, 4500, 2500, 2, 8, 60, 1,
     ["Wi-Fi", "Full kitchen", "Shower", "Air conditioning", "Natural light", "Workspace"],
     "Bright top-floor loft with a full kitchen and a rain shower. Perfect between flights, for a mid-day reset, or a quiet afternoon of work by the window."),
    ("Quiet studio near Penn Station", 0, 1, 1, "New York", "Midtown", 2, 3200, 1500, 1, 6, 30, 1,
     ["Wi-Fi", "Shower", "Air conditioning", "Workspace", "Self check-in", "Blackout curtains"],
     "Two blocks from Penn Station. Nap, shower, take a call, and go. Self check-in with a keypad."),
    ("Two-bedroom with a terrace", 2, 1.5, 3, "New York", "Park Slope", 6, 7500, 4000, 3, 10, 90, 0,
     ["Wi-Fi", "Full kitchen", "Balcony", "TV", "Washer / dryer", "Pet friendly", "Crib"],
     "A calm family flat with a private terrace. Ideal for a daytime gathering, a birthday lunch or a long layover with kids. Host approval required."),
    ("Riverside one-bedroom", 1, 1, 2, "New York", "Long Island City", 3, 4000, 2000, 2, 8, 60, 1,
     ["Wi-Fi", "Full kitchen", "Shower", "Elevator", "Doorman", "Gym access", "Pool access"],
     "Doorman building with skyline views, gym and pool access included with your booking."),
    ("Designer studio in SoMa", 0, 1, 1, "San Francisco", "SoMa", 2, 3600, 1500, 1, 8, 30, 1,
     ["Wi-Fi", "Workspace", "Coffee & tea", "Shower", "Heating", "Self check-in"],
     "A small, very well-designed studio with a proper desk and fast Wi-Fi. Great for focused work or resting before a red-eye."),
    ("Victorian flat with a garden", 2, 1, 2, "San Francisco", "Mission", 5, 6500, 3500, 3, 9, 60, 1,
     ["Wi-Fi", "Full kitchen", "Washer / dryer", "TV", "Natural light", "Pet friendly"],
     "Classic bay windows, a big kitchen and a private garden out back. Bring the dog."),
    ("Hayes Valley one-bedroom", 1, 1, 1, "San Francisco", "Hayes Valley", 3, 4200, 2000, 2, 8, 45, 1,
     ["Wi-Fi", "Shower", "Bathtub", "Heating", "Bed linens", "Coffee & tea"],
     "Deep soaking tub, crisp linens, walking distance to everything. Popular for post-flight recovery."),
    ("Three-bedroom penthouse", 3, 2, 4, "San Francisco", "Nob Hill", 8, 12000, 6000, 4, 10, 120, 0,
     ["Wi-Fi", "Full kitchen", "Balcony", "TV", "Elevator", "Doorman", "Parking", "Washer / dryer"],
     "Top-floor flat with wraparound views. Suits a daytime celebration, a photo shoot or a team offsite. Requests reviewed within the hour."),
    ("Mid-century apartment with a pool", 2, 2, 3, "Los Angeles", "Silver Lake", 6, 6500, 3500, 3, 8, 90, 1,
     ["Wi-Fi", "Full kitchen", "Shower", "Air conditioning", "Parking", "Pet friendly", "Pool access"],
     "Rest, shoot content or host a small daytime gathering. Saltwater pool, big kitchen island and a quiet street."),
    ("Downtown loft near the arena", 1, 1, 1, "Los Angeles", "Downtown", 4, 4800, 2500, 2, 8, 60, 1,
     ["Wi-Fi", "Air conditioning", "TV", "Elevator", "Parking", "Self check-in"],
     "Concrete floors, tall windows, five minutes from the arena. Pre-game, post-game, or a quiet afternoon."),
    ("Beach studio in Venice", 0, 1, 1, "Los Angeles", "Venice", 2, 3800, 1500, 2, 6, 30, 1,
     ["Wi-Fi", "Shower", "Bed linens", "Bathtub", "Natural light"],
     "One block from the sand. Rinse off, nap, work with the windows open."),
    ("Family apartment in Los Feliz", 3, 2, 5, "Los Angeles", "Los Feliz", 8, 9000, 5000, 3, 10, 120, 0,
     ["Wi-Fi", "Full kitchen", "Washer / dryer", "TV", "Crib", "Parking", "Air conditioning"],
     "Space for the whole family between check-out and an evening flight. Crib and high chair available."),
    ("Cozy studio in Wicker Park", 0, 1, 1, "Chicago", "Wicker Park", 2, 2600, 1000, 1, 8, 30, 1,
     ["Wi-Fi", "Heating", "Shower", "Coffee & tea", "Self check-in"],
     "Small, warm and spotless. Right on the Blue Line to O'Hare."),
    ("West Loop one-bedroom", 1, 1, 1, "Chicago", "West Loop", 3, 3900, 2000, 2, 10, 60, 1,
     ["Wi-Fi", "Workspace", "TV", "Elevator", "Gym access", "Heating"],
     "Modern building with a gym. A real desk and a real bed for a working stopover."),
    ("Lakeview apartment for day stays", 1, 1, 2, "Chicago", "Lakeview", 3, 3900, 2000, 2, 10, 60, 1,
     ["Wi-Fi", "Full kitchen", "Shower", "Heating", "Air conditioning", "Elevator"],
     "Between check-out and your evening flight? Nap, shower and work from a calm 12th-floor one-bedroom."),
    ("Logan Square two-bedroom", 2, 1, 2, "Chicago", "Logan Square", 5, 5200, 3000, 3, 9, 60, 1,
     ["Wi-Fi", "Full kitchen", "Washer / dryer", "TV", "Natural light", "Pet friendly"],
     "Sunny corner flat with a big table. Good for a group lunch or a daytime co-working session."),
]

REVIEW_TEXTS = [
    "Exactly as described, host answered within minutes. Will book again.",
    "Clean, quiet and easy to find. The hourly pricing made it a no-brainer.",
    "Great space. Only wish the minimum was a bit shorter, but that's on me.",
    "Perfect for our interviews. Coffee was a nice touch.",
    "Loved it. Check-in instructions were clear and the room was spotless.",
    "Solid value. Wi-Fi was fast and the host left extra towels.",
]


def seed(reset: bool = False) -> None:
    if reset and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()
    conn = connect()
    if conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]:
        print("Database already has data. Use --reset to start over.")
        return
    pw = hash_password(PASSWORD)
    host_ids = [conn.execute("INSERT INTO users (email, password_hash, name, is_host) VALUES (?,?,?,1)", (e, pw, n)).lastrowid for e, n in HOSTS]
    guest_ids = [conn.execute("INSERT INTO users (email, password_hash, name, is_host) VALUES (?,?,?,0)", (e, pw, n)).lastrowid for e, n in GUESTS]

    today = date.today()
    listing_ids = []
    for i, (title, bedrooms, baths, beds, city, hood, cap, rate, clean, mn, mx, buf, instant, amen, desc) in enumerate(LISTINGS):
        host = host_ids[i % len(host_ids)]
        tz = {"New York": "America/New_York", "Chicago": "America/Chicago"}.get(city, "America/Los_Angeles")
        lid = conn.execute(
            """INSERT INTO listings (host_id, title, description, bedrooms, bathrooms, beds, city, neighborhood, address, capacity, hourly_rate_cents,
               cleaning_fee_cents, min_hours, max_hours, buffer_minutes, instant_book, timezone) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (host, title, desc, bedrooms, baths, beds, city, hood, f"{random.randint(10, 999)} {hood} St", cap, rate, clean, mn, mx, buf, instant, tz),
        ).lastrowid
        listing_ids.append(lid)
        for j in range(3):
            conn.execute("INSERT INTO listing_photos (listing_id, url, sort) VALUES (?,?,?)",
                         (lid, f"https://picsum.photos/seed/hourly{lid}-{j}/1200/800", j))
        conn.executemany("INSERT INTO listing_amenities (listing_id, amenity) VALUES (?,?)", [(lid, a) for a in amen])
        conn.execute("""UPDATE listings SET daily_rate_cents = ?, checkin_from = '08:00', checkin_until = '23:00', cancellation_policy = ?,
                        weekend_hourly_rate_cents = ?, long_stay_discount_pct = ?, size_m2 = ?, floor = ?, house_rules = ?, checkin_instructions = ? WHERE id = ?""",
                     (rate * 14, random.choice(["flexible", "flexible", "moderate", "strict"]), int(rate * 1.2) if random.random() < .5 else 0,
                      random.choice([0, 10, 15]), random.randint(28, 120), str(random.randint(0, 9)),
                      "No smoking. No parties. Quiet after 22:00.", "Key box by the door, code sent 2h before check-in.", lid))
        if random.random() < .5:  # a sample night-time price rule
            conn.execute("""INSERT INTO price_rules (listing_id, label, start_date, end_date, hour_from, hour_until, hourly_rate_cents)
                            VALUES (?, 'Nights', ?, ?, 22, 24, ?)""", (lid, today.isoformat(), (today + timedelta(days=90)).isoformat(), int(rate * .6)))

    # Past bookings with reviews (inserted directly; they predate "now").
    for lid in listing_ids:
        l = dict(conn.execute("SELECT * FROM listings WHERE id = ?", (lid,)).fetchone())
        for k in range(random.randint(1, 5)):
            d = today - timedelta(days=random.randint(5, 90))
            start_h = random.choice([9, 10, 11, 13, 14, 15])
            hrs = max(l["min_hours"], min(l["max_hours"], random.choice([2, 3, 4])))
            start = datetime.combine(d, datetime.min.time()) + timedelta(hours=start_h)
            end = start + timedelta(hours=hrs)
            g = random.choice(guest_ids)
            sub = int(hrs * l["hourly_rate_cents"]); fee = round(sub * .12); payout = sub + l["cleaning_fee_cents"] - round(sub * .03)
            bid = conn.execute(
                """INSERT INTO bookings (listing_id, guest_id, start_at, end_at, guests, hours, subtotal_cents, cleaning_fee_cents,
                   service_fee_cents, total_cents, host_payout_cents, status, payment_status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,'completed','paid',?)""",
                (lid, g, start.strftime("%Y-%m-%dT%H:%M"), end.strftime("%Y-%m-%dT%H:%M"), random.randint(1, l["capacity"]), hrs, sub,
                 l["cleaning_fee_cents"], fee, sub + l["cleaning_fee_cents"] + fee, payout, (start - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")),
            ).lastrowid
            if random.random() < 0.8:
                r = random.choice([5, 5, 5, 4, 4, 3])
                conn.execute("""INSERT INTO reviews (booking_id, listing_id, author_id, rating, body, created_at, cleanliness, accuracy, communication, location, value)
                                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                             (bid, lid, g, r, random.choice(REVIEW_TEXTS), end.strftime("%Y-%m-%dT%H:%M"), r, min(5, r + 1), 5, random.choice([4, 5]), r))

    # A few upcoming bookings through the real booking service so availability shows gaps.
    upcoming = 0
    for lid in listing_ids[:10]:
        l = dict(conn.execute("SELECT * FROM listings WHERE id = ?", (lid,)).fetchone())
        for offset in (1, 2, 4):
            d = today + timedelta(days=offset)
            start = datetime.combine(d, datetime.min.time()) + timedelta(hours=random.choice([10, 13, 16]))
            hrs = random.choice([2, 3, 5, 26, 50])
            end = start + timedelta(hours=hrs)
            try:
                create_booking(conn, lid, random.choice(guest_ids), start.strftime("%Y-%m-%dT%H:%M"), end.strftime("%Y-%m-%dT%H:%M"), 1)
                upcoming += 1
            except Exception:
                pass
    conn.execute("UPDATE users SET is_admin = 1 WHERE email = 'host@example.com'")
    conn.close()
    print(f"Seeded {len(HOSTS)} hosts, {len(GUESTS)} guests, {len(listing_ids)} listings, {upcoming} upcoming bookings.")
    print(f"Log in as guest@example.com or host@example.com with password '{PASSWORD}'.")


if __name__ == "__main__":
    seed(reset="--reset" in sys.argv)
