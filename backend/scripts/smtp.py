"""CLI for sending emails (plain text + HTML) and checking SMTP connectivity.

Usage:
    secretspec run -- uv run python scripts/smtp.py send --to benedith@sunet.se --subject "Hello" --body "Hello from sunet smtp"
    secretspec run -- uv run python scripts/smtp.py send --to user@example.com --subject "Hello" --body "Plain text"
    secretspec run -- uv run python scripts/smtp.py send --to user@example.com --subject "Hello" --html "<h1>Hi</h1>"

# Test which port is reachable
#     nc -zv -w 5 smtp.sunet.se 465
#     nc -zv -w 5 smtp.sunet.se 587
#     nc -zv -w 5 smtp.sunet.se 25
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ill_bridge.common.emails.smtp import send_email
from ill_bridge.config import get_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="smtp", description="SMTP utility CLI.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    send_p = sub.add_parser("send", help="Send a plain-text and/or HTML email.")
    send_p.add_argument("-t", "--to", required=True, help="Recipient address(es).")
    send_p.add_argument("-s", "--subject", required=True, help="Email subject.")
    send_p.add_argument("-b", "--body", default="", help="Plain-text body.")
    send_p.add_argument("--html", help="HTML body string.")
    send_p.add_argument("--html-file", type=Path, help="Path to an HTML file.")
    send_p.add_argument("-f", "--from", dest="sender", help="Sender address.")
    args = parser.parse_args(argv)


    html = args.html or (args.html_file.read_text("utf-8") if args.html_file else None)
    print(f"Sending email to {args.to} with subject '{args.subject}'...")
    settings = get_settings(strict_env=False)
    print("SMTP host:", settings.smtp_host)
    print("SMTP port:", settings.smtp_port)
    print("SMTP username:", settings.smtp_username)
    print("SMTP from:", getattr(settings, "smtp_from", None))
    send_email(
        to=args.to,
        from_=args.sender or getattr(settings, "smtp_from", None) or "noreply@sunet.se",
        subject=args.subject,
        body=args.body or None,
        html=html,
        settings=settings,
    )
    print(f"Sent to {args.to}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
