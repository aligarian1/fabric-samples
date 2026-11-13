"""Delivery channels for queued messages.

``console`` prints, ``file`` writes one text file per message, ``email`` sends
through an SMTP server configured with environment variables.  WhatsApp needs a
Meta Business account and approved message templates, so it is left as a
clearly failing stub until that account exists (see the README).
"""
from __future__ import annotations

import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from typing import Callable, Optional

CHANNELS = ("console", "file", "email", "whatsapp")


class DeliveryError(Exception):
    """A message could not be delivered."""


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")[:60] or "message"


def _send_email(address: str, subject: str, body: str) -> None:
    host = os.environ.get("RERA_TRACKER_SMTP_HOST")
    sender = os.environ.get("RERA_TRACKER_SMTP_FROM")
    if not host or not sender:
        raise DeliveryError("email is not configured: set RERA_TRACKER_SMTP_HOST and RERA_TRACKER_SMTP_FROM")
    message = EmailMessage()
    message["From"] = sender
    message["To"] = address
    message["Subject"] = subject
    message.set_content(body)
    port = int(os.environ.get("RERA_TRACKER_SMTP_PORT", "587"))
    user = os.environ.get("RERA_TRACKER_SMTP_USER")
    password = os.environ.get("RERA_TRACKER_SMTP_PASSWORD")
    try:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.starttls(context=ssl.create_default_context())
            if user and password:
                server.login(user, password)
            server.send_message(message)
    except (smtplib.SMTPException, OSError) as error:
        raise DeliveryError("email to %s failed: %s" % (address, error)) from error


def deliver(
    channel: str,
    address: str,
    subject: str,
    body: str,
    message_id: int = 0,
    outbox_dir: str = "outbox",
    out: Optional[Callable[[str], None]] = None,
) -> None:
    """Deliver one message or raise :class:`DeliveryError`."""
    if channel == "console":
        write = out or print
        write("=" * 72)
        write("To: %s" % address)
        write("Subject: %s" % subject)
        write("")
        write(body)
        return
    if channel == "file":
        os.makedirs(outbox_dir, exist_ok=True)
        path = os.path.join(outbox_dir, "%06d-%s.txt" % (message_id, _slug(address)))
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("To: %s\nSubject: %s\n\n%s\n" % (address, subject, body))
        return
    if channel == "email":
        _send_email(address, subject, body)
        return
    if channel == "whatsapp":
        raise DeliveryError("WhatsApp delivery is not set up yet (needs a Meta Business account); see README")
    raise DeliveryError("unknown channel %r" % channel)
