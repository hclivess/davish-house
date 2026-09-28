"""Browser end-to-end flows. Run: .venv/bin/python -m pytest tests/e2e -q"""
import re

import pytest

from tests.e2e.conftest import PASSWORD, day, login

pytestmark = pytest.mark.e2e


def test_home_renders_in_spanish_with_brand(page, server):
    page.goto(server + "/")
    assert "Davish" in page.title()
    assert page.locator("h1").first.inner_text().lower().startswith("apartamentos con precisión horaria")
    assert page.locator("form.searchbar input[name=date]").input_value() != ""       # default window filled by JS
    assert page.locator("form.searchbar input[name=start]").input_value().endswith(":00")
    assert page.locator("a[href*='wa.me']").count() >= 1                                # WhatsApp contact


def test_language_switch_persists(page, server):
    page.goto(server + "/")
    page.click(".lang-switch a[hreflang=en]")
    page.wait_for_load_state("networkidle")
    assert "apartments with hourly precision" in page.locator("h1").first.inner_text().lower()
    page.goto(server + "/login")
    assert "Welcome back" in page.inner_text("h1")
    page.click(".lang-switch a[hreflang=es]")
    page.wait_for_load_state("networkidle")
    assert "Hola de nuevo" in page.inner_text("h1")


def test_signup_creates_account_and_logs_in(page, server):
    page.goto(server + "/signup")
    page.fill("input[name=name]", "Nuevo Usuario")
    page.fill("input[name=email]", "nuevo@e2e.test")
    page.fill("input[name=password]", PASSWORD)
    page.click("form button.btn-block")
    page.wait_for_load_state("networkidle")
    assert page.locator("a.me").inner_text().strip().endswith("Nuevo Usuario")
    page.goto(server + "/account")
    assert page.locator("input[name=email]").input_value() == "nuevo@e2e.test"


def test_search_and_listing_quote(page, server):
    d = day(3)
    page.goto(f"{server}/search?city=Mérida&date={d}&start=10:00&end_date={d}&end=14:00")
    cards = page.locator(".card h3")
    assert cards.count() == 2
    page.click("text=Departamento #51 · La Florida")
    page.wait_for_load_state("networkidle")
    assert "Detalles de la estancia" in page.inner_text("body")
    # Picker preselected from the search; quote must show the 4h price ($650) and be bookable.
    page.wait_for_selector("#quote:not([hidden])", timeout=8000)
    assert "$650" in page.inner_text("#q-subtotal")
    assert "$650" in page.inner_text("#quote")
    # 10 hours -> capped at the day rate ($950).
    page.fill("#end_at", f"{d}T20:00")
    page.dispatch_event("#end_at", "change")
    page.wait_for_function("document.querySelector('#q-subtotal').textContent.includes('950')", timeout=8000)
    # A third guest adds the extra-guest fee.
    page.fill("#guests", "3")
    page.dispatch_event("#guests", "change")
    page.wait_for_function("!document.querySelector('#q-extra-row').hidden", timeout=8000)
    assert "$100" in page.inner_text("#q-extra")
    assert "Inicia sesión para reservar" in page.inner_text(".book-panel")


def test_guest_books_instant_apartment_then_cancels(page, server):
    login(page, server, "guest@e2e.test")
    d = day(4)
    page.goto(f"{server}/listings/1?date={d}&start=12:00&end_date={d}&end=16:00")
    page.wait_for_selector("#book-btn:not([disabled])", timeout=8000)
    page.click("#book-btn")
    page.wait_for_load_state("networkidle")
    assert re.search(r"/bookings/\d+", page.url)
    body = page.inner_text("body")
    assert "Reserva confirmada" in body and "confirmada" in page.inner_text(".status").lower()
    assert "Total cobrado" in body
    # Same slot is now busy for another attempt.
    page.goto(f"{server}/listings/1?date={d}&start=13:00&end_date={d}&end=17:00")
    page.wait_for_selector("#selection .err", timeout=8000)
    assert "ya no están disponibles" in page.inner_text("#selection")
    # Cancel from the trips page.
    page.goto(server + "/trips")
    page.click(".row >> nth=0")
    page.wait_for_load_state("networkidle")
    page.once("dialog", lambda dlg: dlg.accept())
    page.click("text=Cancelar reserva")
    page.wait_for_load_state("networkidle")
    assert "cancelada" in page.inner_text(".status").lower()


def test_request_to_book_and_host_accepts(page, server):
    login(page, server, "guest@e2e.test")
    d = day(5)
    page.goto(f"{server}/listings/2?date={d}&start=09:00&end_date={d}&end=13:00")
    page.wait_for_selector("#book-btn:not([disabled])", timeout=8000)
    assert "Solicitar reserva" in page.inner_text("#book-btn")
    page.click("#book-btn")
    page.wait_for_load_state("networkidle")
    booking_url = page.url
    assert "pendiente" in page.inner_text(".status").lower()
    page.fill(".msg-form input[name=body]", "Llego a las 9 en punto")
    page.click(".msg-form button")
    page.wait_for_load_state("networkidle")
    assert "Llego a las 9 en punto" in page.inner_text("#messages")
    # Host side.
    page.goto(server + "/logout")
    page.request.post(server + "/logout")
    ctx = page.context
    ctx.clear_cookies()
    login(page, server, "host@e2e.test")
    page.goto(server + "/host")
    assert "Panel de anfitrión" in page.inner_text("h1")
    page.goto(booking_url)
    page.click("button[value=accept]")
    page.wait_for_load_state("networkidle")
    assert "confirmada" in page.inner_text(".status").lower()
    # Calendar shows it as booked on that day.
    page.goto(f"{server}/host/listings/2/calendar?month={d[:7]}")
    assert page.locator(f".mday .cal-booking").count() >= 1


def test_host_edits_price_rule_and_it_applies(page, server):
    ctx = page.context
    ctx.clear_cookies()
    login(page, server, "host@e2e.test")
    d = day(6)
    page.goto(f"{server}/host/listings/1/calendar?month={d[:7]}")
    page.fill("form.rule-form input[name=label]", "Noches")
    page.fill("form.rule-form input[name=start_date]", d)
    page.fill("form.rule-form input[name=end_date]", d)
    page.fill("form.rule-form input[name=hourly_rate]", "100")
    page.select_option("form.rule-form select[name=hour_from]", "20")
    page.select_option("form.rule-form select[name=hour_until]", "24")
    page.click("form.rule-form button.btn")
    page.wait_for_load_state("networkidle")
    assert "Noches" in page.inner_text("#rules")
    # 20:00-24:00 at $100/h = $400 (below the $650 4h price because the rule overrides the base rate).
    r = page.request.post(server + "/api/quote", data={"listing_id": 1, "start_at": f"{d}T20:00", "end_at": f"{day(7)}T00:00", "guests": 1})
    assert r.ok and r.json()["subtotal_cents"] == 40000


def test_host_uploads_photo_and_sees_it_on_listing(page, server, tmp_path):
    from PIL import Image
    img = tmp_path / "room.jpg"
    Image.new("RGB", (1600, 1000), (90, 60, 40)).save(img, "JPEG")
    page.context.clear_cookies()
    login(page, server, "host@e2e.test")
    page.goto(server + "/host/listings/1/edit")
    page.set_input_files("input[name=photos]", str(img))
    page.click("form.form-cols button.btn-block")
    page.wait_for_load_state("networkidle")
    assert re.search(r"/listings/1$", page.url)
    src = page.locator(".gallery .gallery-img").first.get_attribute("style")
    assert "/uploads/1/" in src
    assert page.request.get(server + re.search(r"url\('([^']+)'\)", src).group(1)).ok


def test_favorites_and_profile(page, server):
    page.context.clear_cookies()
    login(page, server, "guest@e2e.test")
    page.goto(server + "/listings/1")
    page.click("text=Guardar")
    page.wait_for_load_state("networkidle")
    page.goto(server + "/favorites")
    assert "Departamento #51" in page.inner_text("body")
    page.goto(server + "/users/1")
    assert "Alejandro Davish" in page.inner_text("h1")


def test_admin_panel(page, server):
    page.context.clear_cookies()
    login(page, server, "admin@e2e.test")
    page.goto(server + "/admin")
    assert "Usuarios" in page.inner_text("body")
    page.goto(server + "/admin?tab=listings")
    assert page.locator("table.table tr").count() >= 3


def test_availability_strip_mirrors_and_sets_dates(page, server):
    d1, d2 = day(3), day(5)
    page.goto(f"{server}/listings/1?date={d1}&start=10:00&end_date={d2}&end=10:00")
    page.wait_for_selector("#quote:not([hidden])", timeout=8000)
    assert page.locator(f".cal-day[data-date='{d1}']").evaluate("el => el.classList.contains('sel-start')")
    assert page.locator(f".cal-day[data-date='{d2}']").evaluate("el => el.classList.contains('sel-end')")
    assert page.locator(f".cal-day[data-date='{day(4)}']").evaluate("el => el.classList.contains('sel')")
    # Clicking days re-sets check-in and check-out, keeping the times.
    page.click(f".cal-day[data-date='{day(6)}']")
    page.click(f".cal-day[data-date='{day(8)}']")
    assert page.input_value("#start_at") == f"{day(6)}T10:00" and page.input_value("#end_at") == f"{day(8)}T10:00"
    page.wait_for_selector("#quote:not([hidden])", timeout=8000)
    assert page.locator(f".cal-day[data-date='{day(7)}']").evaluate("el => el.classList.contains('sel')")
