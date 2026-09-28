import os
import tempfile

import pytest

_tmp = tempfile.mkdtemp()
os.environ["DAVISH_DB"] = os.path.join(_tmp, "test.db")
os.environ["DAVISH_UPLOAD_DIR"] = os.path.join(_tmp, "uploads")
os.environ["DAVISH_DEFAULT_TZ"] = "UTC"
os.environ["DAVISH_DEFAULT_LANG"] = "en"  # tests assert English text; Spanish is covered by test_i18n

from app import db as dbmod  # noqa: E402
from app import settings  # noqa: E402

dbmod.DB_PATH = os.environ["DAVISH_DB"]
settings.DB_PATH = os.environ["DAVISH_DB"]
settings.UPLOAD_DIR = os.environ["DAVISH_UPLOAD_DIR"]
settings.DEFAULT_TZ = "UTC"
settings.DEFAULT_STAY_HOURS = 2
settings.GUEST_FEE_PCT, settings.HOST_FEE_PCT = 12, 3   # fee maths is covered by tests

from app import i18n  # noqa: E402

i18n.DEFAULT_LANG = "en"
i18n.set_lang("en")

from app.auth import hash_password  # noqa: E402
from app.db import connect, init_db  # noqa: E402


@pytest.fixture
def conn():
    if os.path.exists(dbmod.DB_PATH):
        os.remove(dbmod.DB_PATH)
    init_db()
    c = connect()
    pw = hash_password("password123")
    c.execute("INSERT INTO users (id, email, password_hash, name, is_host) VALUES (1, 'host@t.com', ?, 'Host', 1)", (pw,))
    c.execute("INSERT INTO users (id, email, password_hash, name, is_host) VALUES (2, 'guest@t.com', ?, 'Guest', 0)", (pw,))
    c.execute("INSERT INTO users (id, email, password_hash, name, is_host) VALUES (3, 'other@t.com', ?, 'Other', 0)", (pw,))
    c.execute("INSERT INTO users (id, email, password_hash, name, is_host, is_admin) VALUES (4, 'admin@t.com', ?, 'Admin', 1, 1)", (pw,))
    # Listing 1: instant, $50/h, $1000 cleaning, 1h buffer... keep buffer 30 for legacy tests -> use 60 min resolution anyway
    c.execute("""INSERT INTO listings (id, host_id, title, city, capacity, hourly_rate_cents, cleaning_fee_cents, min_hours, max_hours,
                 buffer_minutes, instant_book, timezone, bedrooms, advance_notice_hours, daily_rate_cents)
                 VALUES (1, 1, 'Studio', 'Testville', 4, 5000, 1000, 1, 720, 60, 1, 'UTC', 0, 0, 0)""")
    # Listing 2: request to book, $80/h, min 2h, no buffer, check-in only 09-18
    c.execute("""INSERT INTO listings (id, host_id, title, city, capacity, hourly_rate_cents, cleaning_fee_cents, min_hours, max_hours,
                 buffer_minutes, instant_book, timezone, bedrooms, advance_notice_hours, checkin_from, checkin_until, checkout_from, checkout_until)
                 VALUES (2, 1, 'Boardroom', 'Testville', 10, 8000, 0, 2, 720, 0, 0, 'UTC', 2, 0, '09:00', '18:00', '00:00', '24:00')""")
    yield c
    c.close()


@pytest.fixture
def client(conn):
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def login(client, email="guest@t.com"):
    r = client.post("/login", data={"email": email, "password": "password123", "next": "/"}, follow_redirects=False)
    assert r.status_code == 303
    return client
