"""Stripe Connect Express: onboarding, split charges, reversed refunds, account webhooks (Stripe stubbed)."""
import json

import pytest

from app import bookings as svc
from app import payments
from app.db import row
from tests.conftest import login
from tests.test_payments import DAY, FakeStripe


class FakeConnect(FakeStripe):
    def __init__(self):
        super().__init__()
        self.accounts, self.links, self.last_session_params = {}, [], None
        self.refund_calls = []

    def create_connect_account(self, email, name):
        acct = f"acct_{len(self.accounts) + 1}"
        self.accounts[acct] = {"payouts_enabled": False, "charges_enabled": False, "details_submitted": False, "requirements": ["external_account"]}
        return acct

    def account_onboarding_link(self, acct, refresh, ret):
        self.links.append((acct, refresh, ret))
        return f"https://connect.stripe.test/onboard/{acct}"

    def account_status(self, acct): return dict(self.accounts[acct])
    def express_dashboard_link(self, acct): return f"https://connect.stripe.test/dashboard/{acct}"

    def create_checkout_session(self, booking, listing, email, base_url, destination_account=""):
        self.last_session_params = {"destination": destination_account, "fee": booking["total_cents"] - booking["host_payout_cents"]}
        return super().create_checkout_session(booking, listing, email, base_url)

    def refund(self, pi, amount_cents=None, connected=False):
        self.refund_calls.append((pi, amount_cents, connected))


@pytest.fixture
def connect(monkeypatch):
    fake = FakeConnect()
    monkeypatch.setattr(payments, "configured", lambda: True)
    for name in ("create_checkout_session", "retrieve_session", "capture", "release", "refund", "create_connect_account",
                 "account_onboarding_link", "account_status", "express_dashboard_link"):
        monkeypatch.setattr(payments, name, getattr(fake, name))
    monkeypatch.setattr(payments, "parse_webhook", lambda payload, sig: json.loads(payload))
    return fake


def test_host_onboarding_flow(client, conn, connect):
    login(client, "host@t.com")
    page = client.get("/host/payouts").text
    assert "Connect payouts" in page
    r = client.post("/host/payouts/connect", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "https://connect.stripe.test/onboard/acct_1"
    assert row(conn, "SELECT stripe_account_id FROM users WHERE id = 1")["stripe_account_id"] == "acct_1"
    assert connect.links[0][2].endswith("/host/payouts?connected=1")
    # Back from Stripe, still incomplete.
    assert "Incomplete" in client.get("/host/payouts?connected=1").text
    # Stripe finishes verification -> webhook flips the flag.
    connect.accounts["acct_1"].update(payouts_enabled=True, charges_enabled=True, details_submitted=True, requirements=[])
    r = client.post("/stripe/webhook", content=json.dumps({"type": "account.updated", "data": {"object": {"id": "acct_1", "payouts_enabled": True}}}))
    assert r.status_code == 200 and "payouts_enabled=True" in r.json()["result"]
    page = client.get("/host/payouts").text
    assert "Automatic" in page and "Open Stripe payout dashboard" in page
    r = client.post("/host/payouts/dashboard", follow_redirects=False)
    assert r.headers["location"].endswith("/dashboard/acct_1")


def test_charge_is_split_to_connected_host(client, conn, connect):
    conn.execute("UPDATE users SET stripe_account_id = 'acct_9', stripe_payouts_enabled = 1 WHERE id = 1")
    login(client)
    r = client.post("/api/bookings", json={"listing_id": 1, "start_at": f"{DAY}T10:00", "end_at": f"{DAY}T12:00"})
    assert r.status_code == 201
    assert connect.last_session_params["destination"] == "acct_9"
    b = row(conn, "SELECT * FROM bookings WHERE id = ?", (r.json()["id"],))
    assert b["stripe_destination"] == "acct_9" and b["payout_status"] == "automatic"
    assert connect.last_session_params["fee"] == b["total_cents"] - b["host_payout_cents"] > 0   # 12% + 3% in tests
    # Refund after payment reverses the transfer.
    connect.complete("cs_test_1"); svc.sync_payment(conn, b["id"])
    svc.cancel(conn, b["id"], 2)
    assert connect.refund_calls == [("pi_test_1", None, True)]


def test_unconnected_host_gets_manual_payout(client, conn, connect):
    login(client)
    r = client.post("/api/bookings", json={"listing_id": 1, "start_at": f"{DAY}T10:00", "end_at": f"{DAY}T12:00"})
    b = row(conn, "SELECT * FROM bookings WHERE id = ?", (r.json()["id"],))
    assert connect.last_session_params["destination"] == "" and b["payout_status"] == "pending"
    connect.complete("cs_test_1"); svc.sync_payment(conn, b["id"])
    client.post("/logout"); login(client, "admin@t.com")
    page = client.get("/host/payouts").text
    assert "manual payout pending" in page and "Mark paid" in page
    assert client.post(f"/admin/bookings/{b['id']}/paid-manually", follow_redirects=False).status_code == 303
    assert "paid by transfer" in client.get("/host/payouts").text
    assert "payouts: manual" in client.get("/admin?tab=users").text
