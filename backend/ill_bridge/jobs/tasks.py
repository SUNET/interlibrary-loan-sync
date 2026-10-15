import os
import smtplib
from email.message import EmailMessage

import procrastinate

from ill_bridge.jobs.app import app, settings
from ill_bridge.jobs.outgoing_loans import configure_logging, poll_enabled_providers


@app.task(
    queue="provider",
    name="poll_libris_lending",
    retry=procrastinate.RetryStrategy(
        max_attempts=3,
        wait=30,
        exponential_wait=2,
    ),
)
async def poll_libris_lending() -> None:
    """Run one Libris lending provider polling cycle."""
    configure_logging()
    await poll_enabled_providers()


# Procrastinate's cron accepts an optional 6th column for SECONDS, so the
# 30-60s polling target in the SLO is expressible directly — no self-
# rescheduling loop, no offset tasks.
# @app.periodic(cron="*/30 * * * * *")  # every 30 seconds
# @app.task(queue="provider", name="dispatch_due_work")
# async def dispatch_due_work(timestamp: int) -> None:
#     print(f"dispatch_due_work at: {timestamp}")


@app.task(queue="test", name="send_email")
def send_email(to: str, subject: str, body: str):
    message = EmailMessage()

    message["From"] = "noreply@example.com"
    message["To"] = to
    message["Subject"] = subject

    message.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
        smtp.send_message(message)


@app.task(queue="test", name="ping")
async def ping() -> str:
    """Part 2 smoke task: proves the schema, worker and routing are wired."""
    print("PING: Procrastinate worker executed ping")
    return "pong"
