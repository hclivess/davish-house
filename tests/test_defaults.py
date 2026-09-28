from datetime import datetime
from unittest.mock import patch

from app.routes.pages import default_window


def test_default_window_rounds_up_to_the_hour_and_lasts_two_hours():
    with patch("app.routes.pages.local_now", return_value=datetime(2026, 10, 2, 9, 10)):
        assert default_window() == {"date": "2026-10-02", "start": "11:00", "end_date": "2026-10-02", "end": "13:00"}
    with patch("app.routes.pages.local_now", return_value=datetime(2026, 10, 2, 9, 0)):
        assert default_window() == {"date": "2026-10-02", "start": "10:00", "end_date": "2026-10-02", "end": "12:00"}


def test_default_window_may_cross_midnight():
    with patch("app.routes.pages.local_now", return_value=datetime(2026, 10, 2, 22, 40)):
        assert default_window() == {"date": "2026-10-03", "start": "00:00", "end_date": "2026-10-03", "end": "02:00"}


def test_home_and_search_prefill_window(client):
    with patch("app.routes.pages.local_now", return_value=datetime(2026, 10, 2, 9, 10)):
        html = client.get("/?lang=en").text
        assert 'name="date" min="2026-10-02" value="2026-10-02"' in html and 'name="start" step="3600" value="11:00"' in html
        html = client.get("/search").text
        assert 'value="11:00"' in html and 'value="13:00"' in html and "Pick a check-in" in html   # prefilled, unfiltered
