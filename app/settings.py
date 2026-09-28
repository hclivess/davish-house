"""Runtime configuration from environment variables (see deploy/env.example)."""
from __future__ import annotations

import os
import secrets
import warnings

SECRET = os.environ.get("DAVISH_SECRET") or ""
if not SECRET:
    SECRET = secrets.token_hex(32)
    warnings.warn("DAVISH_SECRET is not set; sessions will not survive a restart. Set it in the environment.")

DB_PATH = os.environ.get("DAVISH_DB") or os.path.join(os.path.dirname(__file__), "..", "davish.db")
BASE_URL = os.environ.get("DAVISH_BASE_URL", "http://localhost:8000").rstrip("/")
SECURE_COOKIES = BASE_URL.startswith("https://")
DEFAULT_TZ = os.environ.get("DAVISH_DEFAULT_TZ", "UTC")
SITE_NAME = os.environ.get("DAVISH_SITE_NAME", "Davish's House")
UPLOAD_DIR = os.environ.get("DAVISH_UPLOAD_DIR") or os.path.join(os.path.dirname(DB_PATH), "uploads")
MAX_PHOTOS = 20
MAX_PHOTO_BYTES = 12 * 1024 * 1024

STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
CURRENCY = os.environ.get("DAVISH_CURRENCY", "MXN")
DEFAULT_STAY_HOURS = int(os.environ.get("DAVISH_DEFAULT_STAY_HOURS", "4"))
GUEST_FEE_PCT = float(os.environ.get("DAVISH_GUEST_FEE_PCT", "0"))   # service fee charged to guests on top of the host price
HOST_FEE_PCT = float(os.environ.get("DAVISH_HOST_FEE_PCT", "0"))     # commission deducted from host payouts
PHONE = os.environ.get("DAVISH_PHONE", "")
WHATSAPP = os.environ.get("DAVISH_WHATSAPP", "")  # digits only, international format

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER or "no-reply@localhost")
SMTP_TLS = os.environ.get("SMTP_TLS", "starttls")  # starttls | ssl | none
