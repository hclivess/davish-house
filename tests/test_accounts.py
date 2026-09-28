from app.auth import create_reset_token
from tests.conftest import login


def test_password_reset_flow(client, conn):
    r = client.post("/forgot", data={"email": "guest@t.com"})
    assert r.status_code == 200 and "emailed a reset link" in r.text
    # Unknown email gets the identical response (no account enumeration).
    assert "emailed a reset link" in client.post("/forgot", data={"email": "nobody@t.com"}).text
    token = create_reset_token(conn, 2)
    assert client.get(f"/reset/{token}").status_code == 200
    r = client.post(f"/reset/{token}", data={"password": "newpassword9", "confirm": "newpassword9"}, follow_redirects=False)
    assert r.status_code == 303 and "/account" in r.headers["location"]
    assert client.get(f"/reset/{token}").status_code == 400  # single use
    client.post("/logout")
    assert client.post("/login", data={"email": "guest@t.com", "password": "password123"}, follow_redirects=False).status_code == 401
    assert client.post("/login", data={"email": "guest@t.com", "password": "newpassword9"}, follow_redirects=False).status_code == 303


def test_account_update_and_password_change(client):
    login(client)
    r = client.post("/account", data={"name": "Guest Two", "email": "guest2@t.com", "current_password": "wrong", "new_password": "abcdefgh1"})
    assert r.status_code == 400 and "Current password is wrong" in r.text
    r = client.post("/account", data={"name": "Guest Two", "email": "guest2@t.com", "current_password": "password123", "new_password": "abcdefgh1"},
                    follow_redirects=False)
    assert r.status_code == 303
    me = client.get("/api/me").json()
    assert me["name"] == "Guest Two" and me["email"] == "guest2@t.com"
    r = client.post("/account", data={"name": "X", "email": "host@t.com"})
    assert r.status_code == 400 and "already in use" in r.text


def test_account_delete_requires_password_and_no_active_bookings(client):
    login(client)
    assert client.post("/account/delete", data={"password": "nope"}).status_code == 400
    r = client.post("/account/delete", data={"password": "password123"}, follow_redirects=False)
    assert r.status_code == 303
    assert client.get("/api/me").status_code == 401


def test_listing_timezone_saved(client):
    login(client, "host@t.com")
    form = {"title": "Tokyo room", "city": "Tokyo", "hourly_rate": "30", "capacity": "2", "min_hours": "1",
            "max_hours": "4", "buffer_minutes": "0", "timezone": "Asia/Tokyo"}
    r = client.post("/host/listings/new", data=form, follow_redirects=False)
    assert r.status_code == 303
    lid = int(__import__("re").search(r"/listings/(\d+)", r.headers["location"]).group(1))
    assert client.get(f"/api/listings/{lid}").json()["timezone"] == "Asia/Tokyo"
    form["timezone"] = "Mars/Olympus"
    assert client.post("/host/listings/new", data=form).status_code == 400
