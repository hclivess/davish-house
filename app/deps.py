"""Shared FastAPI dependencies and template setup."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Iterator

from fastapi import Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates

import os

from . import settings
from .auth import current_user
from .availability import format_duration
from .catalog import AMENITIES, APARTMENT_SIZES, WEEKDAYS, size_label
from .icons import icon
from .i18n import LANGUAGES, _, get_lang
from .db import connect
from .pricing import money
import hashlib as _hashlib

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def _fmt_time(iso: str) -> str:
    """'2026-10-02T14:30' -> '2:30 PM'"""
    d = datetime.strptime(iso, "%Y-%m-%dT%H:%M")
    return d.strftime("%-I:%M %p")


def _fmt_date(iso: str) -> str:
    d = datetime.strptime(iso[:10], "%Y-%m-%d")
    if get_lang() == "es":
        return f"{_(d.strftime('%a'))} {d.day} {_(d.strftime('%b') if d.strftime('%b') != 'Mar' else 'Mar_')} {d.year}"
    return d.strftime("%a, %b %-d %Y")


def _fmt_hhmm(hhmm: str) -> str:
    if hhmm == "24:00":
        return _("midnight")
    return datetime.strptime(hhmm, "%H:%M").strftime("%-I:%M %p").replace(":00", "")


templates.env.filters["money"] = lambda c: money(c) + (f" {settings.CURRENCY}" if settings.CURRENCY and settings.CURRENCY != "USD" else "")
templates.env.filters["money_short"] = money


def _price_label(l: dict) -> str:
    """'$650 MXN / 4 h' for block-priced listings, '$40 MXN / hour' otherwise."""
    mh = l.get("min_hours") or 1
    cur = f" {settings.CURRENCY}" if settings.CURRENCY and settings.CURRENCY != "USD" else ""
    if mh >= 24:
        return f"{money(l['daily_rate_cents'] or l['hourly_rate_cents'] * 24)}{cur} / {_('day')}"
    if mh > 1:
        return f"{money(round(l['hourly_rate_cents'] * mh))}{cur} / {mh:g} h"
    return f"{money(l['hourly_rate_cents'])}{cur} {_('/ hour')}"


templates.env.filters["price_label"] = _price_label


def _qs(q: dict, **over) -> str:
    from urllib.parse import urlencode
    merged = {**(q or {}), **over}
    return urlencode({k: v for k, v in merged.items() if v not in ("", None)})


templates.env.globals["qs"] = _qs
templates.env.globals["CURRENCY"] = settings.CURRENCY
templates.env.globals["DEFAULT_STAY_HOURS"] = settings.DEFAULT_STAY_HOURS
templates.env.globals["PHONE"] = settings.PHONE
templates.env.globals["WHATSAPP"] = settings.WHATSAPP
templates.env.filters["ftime"] = _fmt_time
templates.env.filters["fdate"] = _fmt_date
templates.env.filters["fhhmm"] = _fmt_hhmm
templates.env.globals["SIZES"] = APARTMENT_SIZES
templates.env.globals["icon"] = icon
templates.env.globals["_"] = _
templates.env.globals["SITE_NAME"] = settings.SITE_NAME


def _asset_version() -> str:
    h = _hashlib.sha1()
    static = os.path.join(os.path.dirname(__file__), "static")
    for name in sorted(os.listdir(static)):
        p = os.path.join(static, name)
        if os.path.isfile(p):
            h.update(name.encode()); h.update(str(int(os.path.getmtime(p))).encode())
    return h.hexdigest()[:10]


ASSET_VERSION = _asset_version()
templates.env.globals["asset"] = lambda path: f"{path}?v={ASSET_VERSION}"
templates.env.globals["LANGUAGES"] = LANGUAGES
templates.env.globals["get_lang"] = get_lang
templates.env.filters["size"] = lambda b: _(size_label(b))
templates.env.filters["t"] = _
templates.env.filters["duration"] = lambda h: format_duration(h, get_lang())
templates.env.globals["AMENITIES"] = AMENITIES
templates.env.globals["WEEKDAYS"] = WEEKDAYS


def db() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def user(request: Request, conn: sqlite3.Connection = Depends(db)) -> dict | None:
    return current_user(request, conn)


def require_user(u: dict | None = Depends(user)) -> dict:
    if not u:
        raise HTTPException(status_code=401, detail=_("Sign in required"))
    return u


def require_host(u: dict = Depends(require_user)) -> dict:
    if not u["is_host"]:
        raise HTTPException(status_code=403, detail=_("Host account required"))
    return u


def render(request: Request, name: str, ctx: dict | None = None, status_code: int = 200):
    ctx = dict(ctx or {})
    ctx["request"] = request
    ctx["lang"] = get_lang()
    for key in ("error", "message"):
        if isinstance(ctx.get(key), str):
            ctx[key] = _(ctx[key])
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)
