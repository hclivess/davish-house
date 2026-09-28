"""Hourly: an hourly-rental marketplace. Run with `uvicorn app.main:app --reload`."""
from __future__ import annotations

import os

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

import os as _os

from . import settings
from .db import init_db
from .i18n import LANG_COOKIE, LANGUAGES, negotiate, set_lang
from .deps import render
from .routes import api, pages

@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.SITE_NAME, description="Apartments with hourly precision.", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
_os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")
app.include_router(api.router)
app.include_router(api.webhook_router)
app.include_router(pages.router)


@app.middleware("http")
async def language_middleware(request: Request, call_next):
    query_lang = request.query_params.get("lang")
    lang = negotiate(query_lang, request.cookies.get(LANG_COOKIE), request.headers.get("accept-language"))
    set_lang(lang)
    response = await call_next(request)
    if query_lang in LANGUAGES and request.cookies.get(LANG_COOKIE) != query_lang:
        response.set_cookie(LANG_COOKIE, query_lang, max_age=60 * 60 * 24 * 365, samesite="lax", path="/")
    return response


@app.exception_handler(StarletteHTTPException)
async def html_errors(request: Request, exc: StarletteHTTPException):
    """API paths get JSON; page paths get a rendered error page."""
    if request.url.path.startswith(("/api", "/stripe")) or request.url.path in ("/docs", "/openapi.json"):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    if exc.status_code == 401:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(f"/login?next={request.url.path}", status_code=303)
    return render(request, "error.html", {"user": None, "message": str(exc.detail)}, exc.status_code)
