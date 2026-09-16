import os

from ill_bridge.jobs.app import app, settings
import procrastinate
import smtplib
from email.message import EmailMessage


@app.task(
    queue="provider",
    name="poll_provider",
    # Procrastinate retries by policy rather than by exception handling.
    retry=procrastinate.RetryStrategy(
        max_attempts=6,
        wait=5,  # seconds
        exponential_wait=2,  # 5, 10, 20, 40, 80, 160
    ),
)
async def poll_provider(cursor_row_id: str) -> None:
    """Fetch one page from a provider feed and capture it durably."""
    print(f"poll_provider at: {cursor_row_id}")


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
