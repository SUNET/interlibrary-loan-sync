import procrastinate

from ill_bridge.common.emails.smtp import send_email
from ill_bridge.config import get_settings
from ill_bridge.jobs.app import create_procrastinate_app
from ill_bridge.jobs.dispatch_effects import run_dispatch_effects_cycle
from ill_bridge.jobs.outgoing_loans import configure_logging, poll_enabled_providers

app = create_procrastinate_app()


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


@app.task(
    queue="provider",
    name="dispatch_effects",
    retry=procrastinate.RetryStrategy(
        max_attempts=3,
        wait=30,
        exponential_wait=2,
    ),
)
async def dispatch_effects_task() -> None:
    """Run one effect queue dispatch cycle."""
    configure_logging()
    await run_dispatch_effects_cycle()


# Procrastinate's cron accepts an optional 6th column for SECONDS, so the
# 30-60s polling target in the SLO is expressible directly — no self-
# rescheduling loop, no offset tasks.
# @app.periodic(cron="*/30 * * * * *")  # every 30 seconds
# @app.task(queue="provider", name="dispatch_due_work")
# async def dispatch_due_work(timestamp: int) -> None:
#     print(f"dispatch_due_work at: {timestamp}")


@app.task(queue="test", name="send_email")
def send_email_test(to: str, subject: str, body: str) -> None:
    send_email(
        to=to,
        from_="noreply@example.com",
        subject=subject,
        body=body,
    )


@app.task(queue="provider", name="send_email_production")
def send_email_prod(
    to: str,
    subject: str,
    body: str = "",
    *,
    html: str | None = None,
    sender: str | None = None,
) -> None:
    """Send a plain-text and/or HTML email."""
    settings = get_settings(strict_env=False)
    send_email(
        to=to,
        from_=sender or getattr(settings, "smtp_from", None) or "noreply@sunet.se",
        subject=subject,
        body=body or None,
        html=html,
        settings=settings,
    )


@app.task(queue="test", name="ping")
async def ping() -> str:
    """Part 2 smoke task: proves the schema, worker and routing are wired."""
    print("PING: Procrastinate worker executed ping")
    return "pong"
