"""CLI for sending emails (plain text + HTML) and checking SMTP connectivity.

Usage:
    secretspec run -- uv run python scripts/smtp.py send --to benedith@sunet.se --subject "Hello" --body "Hello from sunet smtp"
    secretspec run -- uv run python scripts/smtp.py send --to user@example.com --subject "Hello" --body "Plain text"
    secretspec run -- uv run python scripts/smtp.py send --to user@example.com --subject "Hello" --html "<h1>Hi</h1>" --ssl
    secretspec run -- uv run python scripts/smtp.py ping --ssl
# Test which port is reachable
#     nc -zv -w 5 smtp.sunet.se 465
#     nc -zv -w 5 smtp.sunet.se 587
#     nc -zv -w 5 smtp.sunet.se 25
"""

from __future__ import annotations

import smtplib
from collections.abc import Generator
from contextlib import contextmanager
from email.message import EmailMessage

from ill_bridge.common.emails.html_parser import EmailHTMLSanitizer
from ill_bridge.config import Settings, get_settings


def _expect(result: tuple[int, bytes], code_expected: int, err_msg: str) -> None:
    code, response = result
    if code != code_expected:
        raise RuntimeError(f"{err_msg}: {code} {response.decode(errors='replace')}")


@contextmanager
def open_smtp(
    settings: Settings | None = None,
    *,
    debug: bool = False,
) -> Generator[smtplib.SMTP, None, None]:
    settings = settings or get_settings(strict_env=False)

    ssl_transport: dict[int, type[smtplib.SMTP]] = {
        465: smtplib.SMTP_SSL,
        587: smtplib.SMTP,
        25: smtplib.SMTP,
    }
    if settings.smtp_port not in ssl_transport:
        raise ValueError(f"Unknown SMTP port: {settings.smtp_port}")

    cls = ssl_transport[settings.smtp_port]

    with cls(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        _expect(smtp.ehlo(), 250, "EHLO failed")

        # STARTTLS for port 587
        if cls is smtplib.SMTP and settings.smtp_port == 587:
            if not smtp.has_extn("starttls"):
                raise RuntimeError("Server does not support STARTTLS")
            _expect(smtp.starttls(), 220, "STARTTLS failed")
            _expect(smtp.ehlo(), 250, "EHLO after STARTTLS failed")

        # Authenticate if credentials are present
        if settings.smtp_username and settings.smtp_secret:
            if not smtp.has_extn("auth"):
                raise RuntimeError("SMTP server does not support AUTH")
            _expect(
                smtp.login(
                    settings.smtp_username,
                    settings.smtp_secret.get_secret_value(),
                ),
                235,
                "SMTP login failed",
            )

        _expect(smtp.noop(), 250, "SMTP NOOP failed")

        if debug:
            print(
                f"SMTP server: {settings.smtp_host}:{settings.smtp_port} "
                f"username: {settings.smtp_username}"
            )
            print("Supported SMTP capabilities:")
            for capability, value in smtp.esmtp_features.items():
                print(f"  {capability.upper():<20} {value or 'Supported'}")

        yield smtp


def create_text_message(
    *,
    to: str,
    from_: str,
    subject: str,
    body: str,
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = from_
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


def create_html_message(
    *,
    to: str,
    from_: str,
    subject: str,
    html: str,
    plain: str | None = None,
) -> EmailMessage:
    """Create a multipart/alternative message (plain + HTML)."""
    msg = EmailMessage()
    msg["From"] = from_
    msg["To"] = to
    msg["Subject"] = subject

    # Always provide a plain-text part
    plain_text = plain or "This email requires an HTML-capable client."
    msg.set_content(plain_text)

    clean_html = EmailHTMLSanitizer.clean(html)
    msg.add_alternative(clean_html, subtype="html")
    return msg


def send_email(
    *,
    to: str,
    from_: str,
    subject: str,
    body: str | None = None,
    html: str | None = None,
    settings: Settings | None = None,
    debug: bool = False,
) -> None:
    """
    Send an email.

    Provide either `body` (plain text), `html`, or both.
    When both are given, a proper multipart/alternative message is built.
    """
    settings = settings or get_settings(strict_env=False)
    if not body and not html:
        raise ValueError("Either body or html must be provided")

    if html:
        message = create_html_message(
            to=to,
            from_=from_,
            subject=subject,
            html=html,
            plain=body,
        )
    else:
        message = create_text_message(
            to=to,
            from_=from_,
            subject=subject,
            body=body or "",
        )

    with open_smtp(settings, debug=debug) as smtp:
        smtp.send_message(message)
        if debug:
            print(f"Sent email to {message['To']} with subject '{message['Subject']}'")


def tests():
    def send_email_text() -> None:
        send_email(
            to="benedith@sunet.se",
            from_="noreply@sunet.se",
            subject="Test Email from simplified_email_text()",
            body="This is a test email sent from the simplified_email_text() function.",
        )

    def send_email_html() -> None:
        msg2 = """
        <div style="font-family: Georgia, serif; line-height: 1.3;">
        <span style="display: block; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.15em; color: #b45309; font-family: system-ui, sans-serif;">
            Hello & Welcome
        </span>
        <h1 style="margin: 6px 0 0; font-size: 2.2rem; font-weight: 400; color: #1c1917;">
            Hi, how can we help?
        </h1>
        </div>
        """
        send_email(
            to="benedith@sunet.se",
            from_="noreply@sunet.se",
            subject="Test Email from simplified_email_html()",
            html=msg2,
        )

    send_email_text()
    send_email_html()
    