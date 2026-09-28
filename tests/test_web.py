import io
from datetime import date, timedelta

from PIL import Image

from tests.conftest import login

D = (date.today() + timedelta(days=3)).isoformat()
D2 = (date.today() + timedelta(days=4)).isoformat()


def png_bytes(color=(200, 30, 30), size=(2400, 1600)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def test_home_and_search_render(client):
    assert client.get("/").status_code == 200
    r = client.get("/search", params={"city": "Testville", "date": D, "start": "10:00", "end_date": D2, "end": "12:00"})
    assert r.status_code == 200 and "Studio" in r.text and "Boardroom" in r.text
    assert "Boardroom" not in client.get("/search", params={"bedrooms": 0}).text
    assert "Boardroom" not in client.get("/search", params={"instant": 1}).text
    assert "Studio</h3>" not in client.get("/search", params={"min_rate": 60}).text
    r = client.get("/search", params={"sort": "price_desc", "date": D, "start": "10:00", "end_date": D, "end": "12:00"})
    assert r.text.index("Boardroom</h3>") < r.text.index("Studio</h3>")


def test_search_hides_busy_listings(client):
    login(client)
    r = client.post("/api/bookings", json={"listing_id": 1, "start_at": f"{D}T10:00", "end_at": f"{D2}T12:00"})
    assert r.status_code == 201, r.text
    r = client.get("/api/listings", params={"checkin": f"{D}T11:00", "checkout": f"{D}T13:00"})
    assert [l["id"] for l in r.json()["results"]] == [2]


def test_availability_and_quote_api(client):
    r = client.get("/api/listings/1/availability", params={"from": D, "days": 5})
    assert r.status_code == 200 and len(r.json()["days_summary"]) == 5 and r.json()["days_summary"][0]["hourly_rate_cents"] == 5000
    r = client.post("/api/quote", json={"listing_id": 1, "start_at": f"{D}T10:00", "end_at": f"{D2}T13:00"})
    assert r.status_code == 200 and r.json()["subtotal_cents"] == 27 * 5000
    r = client.post("/api/quote", json={"listing_id": 2, "start_at": f"{D}T20:00", "end_at": f"{D}T23:00"})
    assert r.status_code == 409


def test_booking_requires_login(client):
    assert client.post("/api/bookings", json={"listing_id": 1, "start_at": f"{D}T10:00", "end_at": f"{D}T12:00"}).status_code == 401
    r = client.post("/listings/1/book", data={"start_at": f"{D}T10:00", "end_at": f"{D}T12:00"}, follow_redirects=False)
    assert r.status_code == 303 and "/login" in r.headers["location"]


def test_full_booking_page_flow(client):
    login(client)
    r = client.post("/listings/1/book", data={"start_at": f"{D}T10:00", "end_at": f"{D2}T09:00", "guests": 2, "note": "shoot"}, follow_redirects=False)
    assert r.status_code == 303
    url = r.headers["location"]
    r = client.get(url)
    assert r.status_code == 200 and "re booked!" in r.text
    assert client.get("/trips").status_code == 200
    r = client.post("/listings/1/book", data={"start_at": f"{D}T11:00", "end_at": f"{D}T13:00"})
    assert r.status_code == 409 and "no longer available" in r.text
    bid = url.split("/")[2].split("?")[0]
    assert client.post(f"/bookings/{bid}/messages", data={"body": "hello"}, follow_redirects=False).status_code == 303
    assert "hello" in client.get(f"/bookings/{bid}").text
    r = client.post(f"/bookings/{bid}/cancel", follow_redirects=False)
    assert r.status_code == 303
    assert "cancelled" in client.get(f"/bookings/{bid}").text


def test_host_approval_and_dashboard(client):
    login(client)
    r = client.post("/api/bookings", json={"listing_id": 2, "start_at": f"{D}T10:00", "end_at": f"{D}T12:00"})
    bid = r.json()["id"]
    assert r.json()["status"] == "pending"
    client.post("/logout")
    login(client, "host@t.com")
    assert "Pending" in client.get("/host").text or "pendientes" in client.get("/host").text
    r = client.post(f"/bookings/{bid}/respond", data={"action": "accept"}, follow_redirects=False)
    assert r.status_code == 303
    assert client.get(f"/api/bookings/{bid}").json()["status"] == "confirmed"
    assert client.get("/host/listings/2/calendar").status_code == 200


def test_host_creates_listing_with_photos(client):
    login(client, "host@t.com")
    form = {"title": "New flat", "bedrooms": "2", "bathrooms": "1.5", "beds": "3", "city": "Testville", "hourly_rate": "20", "daily_rate": "300",
            "cleaning_fee": "0", "capacity": "3", "min_hours": "1", "max_hours": "500", "buffer_minutes": "30", "instant_book": "1", "timezone": "UTC",
            "checkin_from": "08:00", "checkin_until": "22:00", "checkout_from": "00:00", "checkout_until": "24:00", "amenities": ["Wi-Fi"],
            "size_m2": "55", "floor": "3", "house_rules": "No parties", "checkin_instructions": "Code 1234", "cancellation_policy": "strict",
            "advance_notice_hours": "1", "max_advance_days": "90", "long_stay_discount_pct": "15", "weekend_hourly_rate": "25"}
    files = [("photos", ("a.png", png_bytes(), "image/png")), ("photos", ("b.png", png_bytes((0, 0, 200)), "image/png"))]
    r = client.post("/host/listings/new", data=form, files=files, follow_redirects=False)
    assert r.status_code == 303, r.text
    lid = int(r.headers["location"].rsplit("/", 1)[1])
    l = client.get(f"/api/listings/{lid}").json()
    assert l["hourly_rate_cents"] == 2000 and l["daily_rate_cents"] == 30000 and l["amenities"] == ["Wi-Fi"]
    assert l["bedrooms"] == 2 and l["size_m2"] == 55 and l["cancellation_policy"] == "strict" and l["weekend_hourly_rate_cents"] == 2500
    assert len(l["photos"]) == 2 and l["photos"][0].startswith("/uploads/")
    img = client.get(l["photos"][0])
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert max(Image.open(io.BytesIO(img.content)).size) <= 1800   # resized
    # Make the second photo the cover, then delete the first.
    pid1, pid2 = [p["id"] for p in l["photo_rows"]]
    client.post(f"/host/listings/{lid}/photos/{pid2}/cover")
    assert client.get(f"/api/listings/{lid}").json()["photo_rows"][0]["id"] == pid2
    client.post(f"/host/listings/{lid}/photos/{pid1}/delete")
    assert len(client.get(f"/api/listings/{lid}").json()["photos"]) == 1
    # Non-image upload is rejected with a message.
    r = client.post(f"/host/listings/{lid}/photos", files=[("photos", ("x.txt", b"nope", "text/plain"))])
    assert r.status_code == 400 and "not an image" in r.text or "no es una imagen" in r.text
    client.post("/logout")
    login(client)
    assert client.get("/host/listings/new").status_code == 403


def test_price_rules_and_calendar(client):
    login(client, "host@t.com")
    r = client.post("/host/listings/1/price-rules", data={"label": "Nights", "start_date": D, "end_date": D2, "hourly_rate": "20",
                                                          "hour_from": "22", "hour_until": "24", "weekday": ["0", "1", "2", "3", "4", "5", "6"]}, follow_redirects=False)
    assert r.status_code == 303
    cal = client.get(f"/host/listings/1/calendar?month={D[:7]}")
    assert cal.status_code == 200 and "Nights" in cal.text
    q = client.post("/api/quote", json={"listing_id": 1, "start_at": f"{D}T21:00", "end_at": f"{D2}T00:00"}).json()
    assert q["subtotal_cents"] == 5000 + 2 * 2000
    assert client.post("/host/listings/1/price-rules", data={"start_date": D2, "end_date": D, "hourly_rate": "20"}, follow_redirects=False).headers["location"].endswith("err=1")
    # block via the calendar
    r = client.post("/host/listings/1/blocks", data={"start_at": f"{D}T00:00", "end_at": f"{D2}T00:00", "reason": "paint"}, follow_redirects=False)
    assert r.status_code == 303
    assert client.post("/api/quote", json={"listing_id": 1, "start_at": f"{D}T10:00", "end_at": f"{D}T12:00"}).status_code == 409


def test_favorites_profile_admin(client, conn):
    login(client)
    assert client.post("/api/favorites/1/toggle").json()["favorite"] is True
    assert "Studio" in client.get("/favorites").text
    assert client.post("/api/favorites/1/toggle").json()["favorite"] is False
    assert client.get("/users/1").status_code == 200 and "Host" in client.get("/users/1").text
    assert client.get("/admin").status_code == 403
    client.post("/logout")
    login(client, "admin@t.com")
    assert client.get("/admin").status_code == 200
    assert client.get("/admin?tab=users&q=guest").status_code == 200
    r = client.post("/admin/users/3/ban", data={"banned": 1}, follow_redirects=False)
    assert r.status_code == 303
    client.post("/logout")
    assert client.post("/login", data={"email": "other@t.com", "password": "password123"}, follow_redirects=False).status_code == 403


def test_reviews_with_categories_and_host_reply(client, conn):
    conn.execute("""INSERT INTO bookings (id, listing_id, guest_id, start_at, end_at, hours, subtotal_cents, cleaning_fee_cents, service_fee_cents,
                    total_cents, host_payout_cents, status, payment_status) VALUES (50, 1, 2, '2026-01-01T10:00', '2026-01-01T12:00', 2, 10000, 1000, 1200, 12200, 10700, 'completed', 'paid')""")
    login(client)
    r = client.post("/bookings/50/review", data={"rating": 5, "body": "Great", "cleanliness": 5, "accuracy": 4, "communication": 5, "location": 3, "value": 4}, follow_redirects=False)
    assert r.status_code == 303
    l = client.get("/api/listings/1").json()
    assert l["review_count"] == 1 and l["category_ratings"]["cleanliness"] == 5 and l["category_ratings"]["location"] == 3
    client.post("/logout")
    login(client, "host@t.com")
    rid = l["reviews"][0]["id"]
    assert client.post(f"/reviews/{rid}/reply", data={"body": "Thanks!"}, follow_redirects=False).status_code == 303
    assert "Thanks!" in client.get("/listings/1").text
    assert client.post("/bookings/50/guest-review", data={"rating": 4, "body": "Tidy guest"}, follow_redirects=False).status_code == 303
    assert "Tidy guest" in client.get("/users/2").text


def test_signup_and_account(client):
    r = client.post("/signup", data={"name": "New", "email": "new@t.com", "password": "password123"}, follow_redirects=False)
    assert r.status_code == 303
    assert client.get("/api/me").json()["email"] == "new@t.com"
    r = client.post("/account", data={"name": "New", "email": "new@t.com", "bio": "Hi there", "phone": "+34 600"},
                    files=[("avatar", ("me.png", png_bytes((0, 200, 0), (300, 300)), "image/png"))], follow_redirects=False)
    assert r.status_code == 303
    me = client.get("/api/me").json()
    assert me["bio"] == "Hi there" and me["avatar_url"].startswith("/uploads/0/")


def test_search_tolerates_empty_query_params(client):
    r = client.get("/search?capacity=&max_rate=&min_rate=&instant=&bedrooms=0&date=&start=&end_date=&end=")
    assert r.status_code == 200 and "Studio</h3>" in r.text
    # Filter links rendered by the page must not carry empty parameters.
    html = client.get("/search").text
    assert "capacity=&" not in html and "max_rate=&" not in html
    for href in __import__("re").findall(r'class="pill[^"]*" href="([^"]+)"', html):
        assert client.get(href.replace("&amp;", "&")).status_code == 200, href
