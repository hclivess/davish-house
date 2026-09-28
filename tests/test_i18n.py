from app.i18n import negotiate
from tests.conftest import login


def test_negotiate_order():
    assert negotiate("es", "en", "en-US") == "es"
    assert negotiate(None, "es", "en-US") == "es"
    assert negotiate(None, None, "es-MX,es;q=0.9,en;q=0.8") == "es"
    from app import i18n
    assert negotiate("fr", None, "de") == i18n.DEFAULT_LANG


def test_pages_render_in_spanish_and_remember_choice(client):
    r = client.get("/?lang=es")
    assert r.status_code == 200 and "Apartamentos con precisión horaria." in r.text and "Explorar por tamaño" in r.text
    assert "davish_lang=es" in r.headers.get("set-cookie", "")
    assert "Iniciar sesión" in client.get("/login").text  # cookie persists the choice
    assert "Restablece tu contraseña" in client.get("/forgot").text
    assert "Explorar apartamentos" in client.get("/search").text
    assert "Detalles de la estancia" in client.get("/listings/1").text
    login(client, "host@t.com")
    assert "Panel de anfitrión" in client.get("/host").text
    assert "Publica tu apartamento" in client.get("/host/listings/new").text or "Publicar anuncio" in client.get("/host/listings/new").text
    assert "Tu cuenta" in client.get("/account").text
    assert "Calendario" in client.get("/host/listings/1/calendar").text


def test_server_messages_translated(client):
    r = client.post("/login?lang=es", data={"email": "x@t.com", "password": "nope"})
    assert r.status_code == 401 and "Correo o contraseña incorrectos." in r.text
    login(client)
    from datetime import date, timedelta
    d = (date.today() + timedelta(days=3)).isoformat()
    r = client.post("/api/quote?lang=es", json={"listing_id": 2, "start_at": f"{d}T07:00", "end_at": f"{d}T09:00"})
    assert r.status_code == 409 and "La entrada solo es posible" in r.json()["detail"]


def test_accept_language_header(client):
    assert "Regístrate" in client.get("/signup", headers={"accept-language": "es-ES,es;q=0.9"}).text or "Registrarse" in client.get("/signup", headers={"accept-language": "es-ES,es;q=0.9"}).text
    assert "Sign up" in client.get("/signup?lang=en").text
