"""Outbound email. Uses SMTP when configured; otherwise logs the message so an operator can act on it."""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from . import settings

log = logging.getLogger("davish.mail")


def send(to: str, subject: str, body: str) -> bool:
    """Returns True if handed to an SMTP server, False if only logged."""
    if not settings.SMTP_HOST:
        log.warning("SMTP not configured. Email to %s | %s\n%s", to, subject, body)
        return False
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.SMTP_FROM, to, subject
    msg.set_content(body)
    try:
        if settings.SMTP_TLS == "ssl":
            server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, context=ssl.create_default_context(), timeout=20)
        else:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20)
            if settings.SMTP_TLS == "starttls":
                server.starttls(context=ssl.create_default_context())
        with server:
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception:  # noqa: BLE001 - never let mail failures break a request
        log.exception("Failed to send email to %s", to)
        return False
