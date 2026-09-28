"""Import Davish's House apartments from the original static site into the platform.

    python import_davish.py --site /path/to/davish-house --host-email alejandro@davish.pro [--host-password ...]

Idempotent: listings are matched by title, photos by source file. Creates the host account if missing.
Prices are MXN from the June 2026 price list: 4-hour price -> hourly rate (price/4, 4h minimum), day price -> daily cap,
month price -> 30-day cap, extra person $100/day beyond 2 (Chicxulub: 4 included).
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys

from app.auth import hash_password
from app.db import connect, init_db, row
from app import photos

FLORIDA = ("La Florida", "C. 23A 335, La Florida, Mérida, Yucatán, C.P. 97138")
MONTES = ("Montes de Amé", "C. 69 156A x 24 y 26, Montes de Amé, Mérida, Yucatán")
CHIC = ("Chicxulub Puerto", "Punta Arena Condominium, C. 17, Chicxulub Puerto, Progreso, Yucatán, C.P. 97330")

SHARED = ["Wi-Fi", "Air conditioning", "Smart TV", "Netflix", "Prime Video", "HBO", "YouTube Premium", "Private bathroom", "Pool access",
          "BBQ grill", "Parking with electric gate", "Toiletries included", "No deposit", "No guarantor", "Self check-in", "Bed linens"]

# key, number/title, area, city, (4h, day, month) MXN, capacity, included, amenities, beds/bedrooms/bathrooms, photo
APARTMENTS = [
    ("51", "Departamento #51 · La Florida", FLORIDA, "Mérida", (650, 950, 17000), 2, 2, ["Queen bed", "Refrigerator", "Coffee maker", "Closet", "Desk"], (1, 0, 1), "depa-51.jpg"),
    ("52", "Departamento #52 · La Florida", FLORIDA, "Mérida", (650, 950, 16000), 2, 2, ["Queen bed", "Balcony", "Bathtub", "Coffee maker", "Refrigerator", "Closet", "Desk"], (1, 0, 1), "depa-52.jpg"),
    ("53", "Departamento #53 · La Florida", FLORIDA, "Mérida", (500, 600, 15000), 2, 2, ["Full bed", "Coffee maker", "Desk", "Closet"], (1, 0, 1), "depa-53.jpg"),
    ("54", "Departamento #54 Premium · La Florida", FLORIDA, "Mérida", (750, 1100, 20000), 2, 2, ["Queen bed", "Full kitchen", "Microwave", "Bathtub", "Private pool"], (1, 0, 1), "depa-54.jpg"),
    ("57", "Departamento #57 · Montes de Amé", MONTES, "Mérida", (650, 1050, 19000), 4, 2, ["2 Queen beds", "Desk", "Microwave", "High-speed Wi-Fi (1 Gbps)"], (2, 0, 1), "depa-57.jpg"),
    ("58", "Departamento #58 · Montes de Amé", MONTES, "Mérida", (650, 950, 17000), 2, 2, ["Queen bed", "Kitchenette", "Desk", "High-speed Wi-Fi (1 Gbps)"], (1, 0, 1), "depa-58.jpg"),
    ("59", "Departamento #59 · Montes de Amé", MONTES, "Mérida", (580, 850, 17000), 2, 2, ["Queen bed", "Closet", "Desk", "Kettle"], (1, 0, 1), "depa-59.jpg"),
    ("64", "Departamento #64 · Montes de Amé", MONTES, "Mérida", (650, 950, 17000), 2, 2, ["Queen bed", "Kitchenette", "Desk", "High-speed Wi-Fi (1 Gbps)"], (1, 0, 1), "depa-64.jpg"),
    ("66", "Departamento #66 · Montes de Amé", MONTES, "Mérida", (500, 700, 10000), 2, 2, ["Queen bed", "Kitchenette", "Desk"], (1, 0, 1), "depa-66.jpg"),
    ("chicxulub", "Departamento Punta Arena · Chicxulub Puerto", CHIC, "Chicxulub Puerto", (None, 2500, 0), 4, 4,
     ["Full bed", "Full kitchen", "Refrigerator", "Microwave", "Coffee maker", "Clothes dryer", "Closet"], (2, 2, 1), "depa-chicxulub.jpg"),
]

HOUSE_RULES_ES = ("Los precios incluyen hasta 2 adultos (Punta Arena: hasta 4). Persona extra: $100 MXN por día o por 4 horas.\n"
                  "Cancelación: 100 % de reembolso con 2 días de anticipación, 50 % con 1 día.\n"
                  "Para confirmar la reserva se requiere comprobante de pago.")
CHECKIN_ES = ("En su primera visita alguien del staff le acompaña y muestra el lugar. En visitas posteriores puede elegir ingresar solo.\n"
              "Estacionamiento con portón eléctrico. Consultas y disponibilidad el mismo día por WhatsApp +52 999 398 2548.")
TITLE_EN = {"51": "Apartment #51 · La Florida", "52": "Apartment #52 · La Florida", "53": "Apartment #53 · La Florida", "54": "Apartment #54 Premium · La Florida",
            "57": "Apartment #57 · Montes de Amé", "58": "Apartment #58 · Montes de Amé", "59": "Apartment #59 · Montes de Amé",
            "64": "Apartment #64 · Montes de Amé", "66": "Apartment #66 · Montes de Amé", "chicxulub": "Punta Arena beach apartment · Chicxulub Puerto"}


def load_texts(site_dir: str) -> dict:
    """Pull the Spanish and English descriptions out of the original site's translation table."""
    import re
    html = open(os.path.join(site_dir, "site", "index.html"), encoding="utf-8").read()
    t = html[html.index("var T = {"):]
    out = {}
    for lang in ("es", "en"):
        block = re.search(r"\n\s*%s: \{(.*?)\n\s*\},?\n\s*(?:[a-z]{2}: \{|\};)" % lang, t, re.S).group(1)
        d = {}
        for k, v in re.findall(r"(\w+): '((?:[^'\\]|\\.)*)'", block):
            d[k] = v.replace("\\'", "'")
        out[lang] = d
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", required=True, help="path to the davish-house repo checkout")
    ap.add_argument("--host-email", default="alejandro@davish.pro")
    ap.add_argument("--host-password", default=None)
    args = ap.parse_args()
    init_db()
    conn = connect()
    texts = load_texts(args.site)

    host = row(conn, "SELECT * FROM users WHERE email = ?", (args.host_email,))
    password = None
    if not host:
        password = args.host_password or secrets.token_urlsafe(10)
        conn.execute("INSERT INTO users (email, password_hash, name, is_host, bio, phone) VALUES (?,?,?,1,?,?)",
                     (args.host_email, hash_password(password), "Alejandro Davish", texts["es"].get("owner_bio", ""), "+52 999 398 2548"))
        host = row(conn, "SELECT * FROM users WHERE email = ?", (args.host_email,))
        avatar = os.path.join(args.site, "site", "img", "profile.jpg")
        if os.path.exists(avatar):
            conn.execute("UPDATE users SET avatar_url = ? WHERE id = ?", (photos.save_upload(0, open(avatar, "rb").read()), host["id"]))
    conn.execute("UPDATE users SET is_host = 1 WHERE id = ?", (host["id"],))

    created = updated = 0
    for key, title, (hood, address), city, (p4, pday, pmonth), capacity, included, amen, (beds, bedrooms, baths), photo in APARTMENTS:
        desc_es = texts["es"].get(f"desc_{key}", "")
        desc_en = texts["en"].get(f"desc_{key}", "")
        description = desc_es + ("\n\n" + desc_en if desc_en and desc_en != desc_es else "")
        hourly = round(p4 / 4 * 100) if p4 else round(pday / 24 * 100)
        data = {
            "host_id": host["id"], "title": title, "description": description, "category": "apartment", "city": city, "neighborhood": hood,
            "address": address, "capacity": capacity, "hourly_rate_cents": hourly, "daily_rate_cents": pday * 100, "monthly_rate_cents": pmonth * 100,
            "cleaning_fee_cents": 0, "min_hours": 4 if p4 else 24, "max_hours": 24 * 90, "buffer_minutes": 60, "instant_book": 1, "timezone": "America/Merida",
            "checkin_from": "00:00", "checkin_until": "24:00", "checkout_from": "00:00", "checkout_until": "24:00",
            "bedrooms": bedrooms, "bathrooms": baths, "beds": beds, "house_rules": HOUSE_RULES_ES, "checkin_instructions": CHECKIN_ES,
            "advance_notice_hours": 1, "max_advance_days": 365, "cancellation_policy": "two_days", "included_guests": included,
            "extra_guest_fee_cents": 10000 if key != "chicxulub" else 0, "status": "active",
        }
        existing = row(conn, "SELECT id FROM listings WHERE title = ? AND host_id = ?", (title, host["id"]))
        if existing:
            lid = existing["id"]
            sets = ", ".join(f"{k} = ?" for k in data)
            conn.execute(f"UPDATE listings SET {sets} WHERE id = ?", (*data.values(), lid))
            updated += 1
        else:
            cols = ", ".join(data); qs = ", ".join("?" * len(data))
            lid = conn.execute(f"INSERT INTO listings ({cols}) VALUES ({qs})", tuple(data.values())).lastrowid
            created += 1
        conn.execute("DELETE FROM listing_amenities WHERE listing_id = ?", (lid,))
        conn.executemany("INSERT OR IGNORE INTO listing_amenities (listing_id, amenity) VALUES (?,?)", [(lid, a) for a in dict.fromkeys(amen + SHARED)])
        if not row(conn, "SELECT 1 AS x FROM listing_photos WHERE listing_id = ?", (lid,)):
            src = os.path.join(args.site, "site", "img", photo)
            if os.path.exists(src):
                url = photos.save_upload(lid, open(src, "rb").read())
                conn.execute("INSERT INTO listing_photos (listing_id, url, sort) VALUES (?,?,0)", (lid, url))
    conn.close()
    print(f"Host: {host['name']} <{args.host_email}> (id {host['id']}); listings created {created}, updated {updated}.")
    if password:
        print(f"Generated password for {args.host_email}: {password}")


if __name__ == "__main__":
    main()
