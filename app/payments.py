"""Stripe integration (Checkout + PaymentIntents).

Instant-book listings: the guest is charged when Checkout completes.
Request-to-book listings: Checkout only *authorizes* the card (manual capture); the charge is captured
when the host accepts and released when the host declines or the request expires.

When STRIPE_SECRET_KEY is empty the platform runs in simulated mode: bookings are marked paid without
a charge. `configured()` tells callers which mode is active.
"""
from __future__ import annotations

import logging
import os

import stripe

log = logging.getLogger("davish.payments")

SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
CURRENCY = os.environ.get("STRIPE_CURRENCY", "usd").lower()
PAYMENT_WINDOW_MINUTES = 30  # slot is held this long while the guest pays

stripe.api_key = SECRET_KEY or None


class PaymentError(Exception):
    pass


def configured() -> bool:
    return bool(SECRET_KEY)


def create_checkout_session(booking: dict, listing: dict, guest_email: str, base_url: str) -> dict:
    """Returns {"id": session_id, "url": hosted_checkout_url, "payment_intent": pi_id | None}."""
    manual = not listing["instant_book"]
    line_items = [{
        "price_data": {"currency": CURRENCY, "unit_amount": booking["subtotal_cents"],
                       "product_data": {"name": listing["title"], "description": f"{booking['hours']:g} hours on {booking['start_at'][:10]}"}},
        "quantity": 1,
    }]
    if booking["cleaning_fee_cents"]:
        line_items.append({"price_data": {"currency": CURRENCY, "unit_amount": booking["cleaning_fee_cents"],
                                          "product_data": {"name": "Cleaning fee"}}, "quantity": 1})
    if booking["service_fee_cents"]:
        line_items.append({"price_data": {"currency": CURRENCY, "unit_amount": booking["service_fee_cents"],
                                          "product_data": {"name": "Service fee"}}, "quantity": 1})
    params = {
        "mode": "payment",
        "line_items": line_items,
        "customer_email": guest_email,
        "client_reference_id": str(booking["id"]),
        "metadata": {"booking_id": str(booking["id"]), "listing_id": str(listing["id"])},
        "success_url": f"{base_url}/bookings/{booking['id']}?paid=1",
        "cancel_url": f"{base_url}/bookings/{booking['id']}?cancelled=1",
        "expires_at": None,
        "payment_intent_data": {"metadata": {"booking_id": str(booking["id"])}, "description": f"Booking #{booking['id']} · {listing['title']}"},
    }
    params.pop("expires_at")
    if manual:
        params["payment_intent_data"]["capture_method"] = "manual"
    try:
        s = stripe.checkout.Session.create(**params)
    except stripe.error.StripeError as e:  # type: ignore[attr-defined]
        log.exception("Stripe checkout session failed for booking %s", booking["id"])
        raise PaymentError(str(e.user_message or e)) from e
    return {"id": s.id, "url": s.url, "payment_intent": s.payment_intent}


def retrieve_session(session_id: str) -> dict:
    """Returns {"payment_status": paid|unpaid|no_payment_required, "status": open|complete|expired, "payment_intent": id|None}."""
    try:
        s = stripe.checkout.Session.retrieve(session_id)
    except stripe.error.StripeError as e:  # type: ignore[attr-defined]
        raise PaymentError(str(e)) from e
    return {"payment_status": s.payment_status, "status": s.status, "payment_intent": s.payment_intent}


def capture(payment_intent_id: str) -> None:
    try:
        stripe.PaymentIntent.capture(payment_intent_id)
    except stripe.error.StripeError as e:  # type: ignore[attr-defined]
        raise PaymentError(str(e)) from e


def release(payment_intent_id: str) -> None:
    """Cancel an uncaptured authorization."""
    try:
        stripe.PaymentIntent.cancel(payment_intent_id)
    except stripe.error.StripeError as e:  # type: ignore[attr-defined]
        raise PaymentError(str(e)) from e


def refund(payment_intent_id: str, amount_cents: int | None = None) -> None:
    try:
        kwargs = {"payment_intent": payment_intent_id}
        if amount_cents is not None:
            kwargs["amount"] = amount_cents
        stripe.Refund.create(**kwargs)
    except stripe.error.StripeError as e:  # type: ignore[attr-defined]
        raise PaymentError(str(e)) from e


def parse_webhook(payload: bytes, signature: str) -> dict:
    """Verify the Stripe signature and return the event as a dict. Raises PaymentError on a bad signature."""
    if not WEBHOOK_SECRET:
        raise PaymentError("STRIPE_WEBHOOK_SECRET is not set")
    try:
        event = stripe.Webhook.construct_event(payload, signature, WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError) as e:  # type: ignore[attr-defined]
        raise PaymentError("Invalid webhook signature") from e
    return event.to_dict_recursive() if hasattr(event, "to_dict_recursive") else dict(event)
