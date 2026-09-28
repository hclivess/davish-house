"""End-to-end fixtures: a real uvicorn server on a temp database, driven by headless Chromium (Playwright)."""
import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import date, timedelta

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PASSWORD = "e2e-password-123"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def server():
    tmp = tempfile.mkdtemp()
    port = _free_port()
    env = {**os.environ, "DAVISH_DB": os.path.join(tmp, "e2e.db"), "DAVISH_UPLOAD_DIR": os.path.join(tmp, "uploads"),
           "DAVISH_SECRET": "e2e-secret", "DAVISH_DEFAULT_LANG": "es", "DAVISH_DEFAULT_TZ": "UTC", "DAVISH_BASE_URL": f"http://127.0.0.1:{port}",
           "DAVISH_SITE_NAME": "Davish's House", "DAVISH_WHATSAPP": "529993982548", "DAVISH_DEFAULT_STAY_HOURS": "4", "STRIPE_SECRET_KEY": ""}
    # Seed: one host with two apartments, one guest, one admin.
    subprocess.run([sys.executable, "-c", """
import os
from app.db import init_db, connect
from app.auth import hash_password
init_db(); c = connect(); pw = hash_password(%r)
c.execute("INSERT INTO users (id,email,password_hash,name,is_host) VALUES (1,'host@e2e.test',?, 'Alejandro Davish',1)", (pw,))
c.execute("INSERT INTO users (id,email,password_hash,name,is_host) VALUES (2,'guest@e2e.test',?, 'Guest Person',0)", (pw,))
c.execute("INSERT INTO users (id,email,password_hash,name,is_host,is_admin) VALUES (3,'admin@e2e.test',?, 'Admin',1,1)", (pw,))
c.execute('''INSERT INTO listings (id,host_id,title,description,city,neighborhood,capacity,hourly_rate_cents,daily_rate_cents,monthly_rate_cents,min_hours,max_hours,
             buffer_minutes,instant_book,timezone,bedrooms,included_guests,extra_guest_fee_cents,cancellation_policy,advance_notice_hours)
             VALUES (1,1,'Departamento #51 · La Florida','Cómodo departamento con cama Queen.','Mérida','La Florida',2,16250,95000,1700000,4,2160,60,1,'UTC',0,2,10000,'two_days',1)''')
c.execute('''INSERT INTO listings (id,host_id,title,description,city,neighborhood,capacity,hourly_rate_cents,daily_rate_cents,min_hours,max_hours,buffer_minutes,instant_book,timezone,bedrooms,advance_notice_hours)
             VALUES (2,1,'Departamento #57 · Montes de Amé','El más amplio.','Mérida','Montes de Amé',4,16250,105000,4,2160,60,0,'UTC',1,1)''')
c.executemany("INSERT INTO listing_amenities (listing_id, amenity) VALUES (?,?)", [(1,'Wi-Fi'),(1,'Netflix'),(2,'Wi-Fi')])
c.close()
""" % PASSWORD], cwd=ROOT, env=env, check=True)
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
                            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    base = f"http://127.0.0.1:{port}"
    import urllib.request
    for _ in range(60):
        try:
            urllib.request.urlopen(base + "/api/health", timeout=1)
            break
        except Exception:
            time.sleep(0.25)
    else:
        proc.kill()
        raise RuntimeError("server did not start: " + proc.stderr.read().decode()[-2000:])
    yield base
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, locale="es-MX")
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.errors = errors
    yield pg
    ctx.close()
    assert not errors, f"JavaScript errors on page: {errors}"


def login(page, base, email):
    page.goto(base + "/login")
    page.fill("input[name=email]", email)
    page.fill("input[name=password]", PASSWORD)
    page.click("form button.btn-block")
    page.wait_for_load_state("networkidle")


def day(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()
