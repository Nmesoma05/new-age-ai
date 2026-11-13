"""Outgoing email. Three honest modes:

- "none" (default): available() is False; callers must tell the user email isn't available.
- "dev_outbox": messages are stored in email_outbox with status captured_dev and are NOT sent. Refused when deployed.
- "smtp": sent through the configured provider's SMTP relay over STARTTLS. The body is never stored or logged (a
  reset email contains a one-time link). A delivery failure is logged and reported to error tracking; the caller's
  answer to the person doesn't change (it must not reveal whether the account exists).
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import get_settings
from app.models import EmailOutbox

log = logging.getLogger("eco.mailer")


def available() -> bool:
    s = get_settings()
    if s.email_backend == "smtp":
        return bool(s.smtp_host and s.email_from)
    return s.email_backend == "dev_outbox" and not s.is_deployed


def _smtp_send(to: str, subject: str, body: str) -> None:
    s = get_settings()
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.email_from, to, subject
    msg.set_content(body)
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
        smtp.starttls(context=ssl.create_default_context())  # refuses plaintext and bad certificates
        if s.smtp_username:
            smtp.login(s.smtp_username, s.smtp_password.get_secret_value() if s.smtp_password else "")
        smtp.send_message(msg)


async def send(db, *, to: str, purpose: str, subject: str, body: str) -> bool:
    """Returns True if handed to the provider (or captured in dev). Never raises on delivery failure."""
    if not available():  # pragma: no cover - callers check first
        raise RuntimeError("no email backend")
    s = get_settings()
    if s.email_backend == "dev_outbox":
        db.add(EmailOutbox(to_email=to, purpose=purpose, subject=subject[:200], body=body[:20000]))
        return True
    try:
        await asyncio.to_thread(_smtp_send, to, subject[:200], body)
        log.info("email sent", extra={"purpose": purpose})
        return True
    except (OSError, smtplib.SMTPException) as e:
        log.error("email delivery failed", extra={"purpose": purpose, "error": type(e).__name__})
        return False
