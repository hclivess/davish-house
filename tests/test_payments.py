"""Stripe flow with the Stripe client stubbed out."""
from datetime import date, timedelta

import pytest

from app import bookings as svc
from app import payments
from app.db import row
from tests.conftest import login

DAY = (date.today() + timedelta(days=3)).isoformat()


class FakeStripe:
    def __init__(self):
        self.sessions, self.captured, self.released, self.refunds = {}, [], [], []
        self.n = 0

    def create_checkout_session(self, booking, listing, email, base_url, destination_account=""):
        self.n += 1
        sid, pi = f"cs_test_{self.n}", f"pi_test_{self.n}"
        self.sessions[sid] = {"payment_status": "unpaid", "status": "open", "payment_intent": pi, "manual": not listing["instant_book"]}
        return {"id": sid, "url": f"https://checkout.stripe.test/{sid}", "payment_intent": pi}

    def retrieve_session(self, sid):
        return self.sessions[sid]

    def capture(self, pi): self.captured.append(pi)
    def release(self, pi): self.released.append(pi)
    def refund(self, pi, amount_cents=None, connected=False): self.refunds.append((pi, amount_cents))

    def complete(self, sid):
        s = self.sessions[sid]
        s["status"] = "complete"
        s["payment_status"] = "unpaid" if s["manual"] else "paid"


@pytest.fixture
def stripe(monkeypatch):
    fake = FakeStripe()
    monkeypatch.setattr(payments, "configured", lambda: True)
    for name in ("create_checkout_session", "retrieve_session", "capture", "release", "refund"):
        monkeypatch.setattr(payments, name, getattr(fake, name))
    monkeypatch.setattr(payments, "parse_webhook", lambda payload, sig: __import__("json").loads(payload))
    return fake


def test_checkout_holds_slot_then_confirms(client, conn, stripe):
    login(client)
    r = client.post("/listings/1/book", data={"start_at": f"{DAY}T10:00", "end_at": f"{DAY}T12:00"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("https://checkout.stripe.test/")
    b = row(conn, "SELECT * FROM bookings")
    assert b["status"] == "awaiting_payment" and b["expires_at"] and b["stripe_session_id"] == "cs_test_1"
    # Slot is held while unpaid.
    assert client.post("/api/quote", json={"listing_id": 1, "start_at": f"{DAY}T11:00", "end_at": f"{DAY}T13:00"}).status_code == 409
    # Webhook confirms it.
    stripe.complete("cs_test_1")
    r = client.post("/stripe/webhook", content=__import__("json").dumps({"id": "evt_1", "type": "checkout.session.completed",
                    "data": {"object": {"metadata": {"booking_id": str(b["id"])}, "payment_intent": "pi_test_1"}}}), headers={"stripe-signature": "x"})
    assert r.status_code == 200 and r.json()["result"] == f"booking {b['id']} paid"
    b = row(conn, "SELECT * FROM bookings")
    assert b["status"] == "confirmed" and b["payment_status"] == "paid" and b["stripe_payment_intent"] == "pi_test_1"
    # Replaying the webhook is harmless.
    client.post("/stripe/webhook", content=__import__("json").dumps({"type": "checkout.session.completed", "data": {"object": {"metadata": {"booking_id": str(b["id"])}}}}))
    assert row(conn, "SELECT status FROM bookings")["status"] == "confirmed"


def test_return_page_syncs_without_webhook(client, conn, stripe):
    login(client)
    r = client.post("/api/bookings", json={"listing_id": 1, "start_at": f"{DAY}T10:00", "end_at": f"{DAY}T12:00"})
    assert r.status_code == 201 and r.json()["checkout_url"].startswith("https://checkout.stripe.test/")
    bid = r.json()["id"]
    stripe.complete("cs_test_1")
    html = client.get(f"/bookings/{bid}?paid=1").text
    assert "re booked!" in html
    assert row(conn, "SELECT status FROM bookings WHERE id = ?", (bid,))["status"] == "confirmed"


def test_request_to_book_authorizes_then_captures_on_accept(client, conn, stripe):
    login(client)
    bid = client.post("/api/bookings", json={"listing_id": 2, "start_at": f"{DAY}T10:00", "end_at": f"{DAY}T12:00"}).json()["id"]
    stripe.complete("cs_test_1")
    svc.sync_payment(conn, bid)
    b = row(conn, "SELECT * FROM bookings WHERE id = ?", (bid,))
    assert b["status"] == "pending" and b["payment_status"] == "authorized"
    svc.host_respond(conn, bid, host_id=1, accept=True)
    assert stripe.captured == ["pi_test_1"]
    assert row(conn, "SELECT status, payment_status FROM bookings WHERE id = ?", (bid,))["payment_status"] == "paid"


def test_decline_releases_authorization(conn, stripe):
    b = svc.create_booking(conn, 2, 2, f"{DAY}T10:00", f"{DAY}T12:00")
    svc.start_checkout(conn, b["id"], "g@t.com", "http://x")
    stripe.complete("cs_test_1")
    svc.sync_payment(conn, b["id"])
    svc.host_respond(conn, b["id"], host_id=1, accept=False)
    assert stripe.released == ["pi_test_1"] and not stripe.captured
    assert row(conn, "SELECT status FROM bookings")["status"] == "declined"


def test_cancel_refunds_when_early_only(conn, stripe):
    b = svc.create_booking(conn, 1, 2, f"{DAY}T10:00", f"{DAY}T12:00")
    svc.start_checkout(conn, b["id"], "g@t.com", "http://x")
    stripe.complete("cs_test_1")
    svc.sync_payment(conn, b["id"])
    b = svc.cancel(conn, b["id"], 2)  # 3 days ahead, flexible policy -> full refund
    assert stripe.refunds == [("pi_test_1", None)] and b["payment_status"] == "refunded" and b["refund_cents"] == b["total_cents"]


def test_unpaid_booking_expires_and_frees_slot(conn, stripe):
    b = svc.create_booking(conn, 1, 2, f"{DAY}T10:00", f"{DAY}T12:00")
    conn.execute("UPDATE bookings SET expires_at = '2000-01-01T00:00' WHERE id = ?", (b["id"],))
    assert svc.expire_unpaid(conn) == 1
    assert row(conn, "SELECT status FROM bookings")["status"] == "expired"
    assert svc.create_booking(conn, 1, 3, f"{DAY}T10:00", f"{DAY}T12:00")["status"] == "awaiting_payment"


def test_bad_webhook_signature_rejected(client, monkeypatch):
    monkeypatch.setattr(payments, "WEBHOOK_SECRET", "whsec_test")
    r = client.post("/stripe/webhook", content=b"{}", headers={"stripe-signature": "bad"})
    assert r.status_code == 400
