import asyncio
import random

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from faker import Faker

from ill_bridge.jobs.app import app as procrastinate_app
from ill_bridge.jobs.tasks import (
    dispatch_due_work,
    ping,
    poll_provider,
    send_email,
)

fake = Faker("sv_SE")
seq = 42
Faker.seed(seq)
rng = random.Random(seq)


async def enqueue_poll_provider():
    await poll_provider.defer_async(cursor_row_id="provider-main")


async def enqueue_dispatch_due_work():
    # Prefer a real wall-clock timestamp if the task expects one
    timestamp = int(asyncio.get_running_loop().time())
    await dispatch_due_work.defer_async(timestamp=timestamp)


async def enqueue_ping():
    await ping.defer_async()


async def enqueue_send_email():
    # Generate values at execution time (not at schedule-definition time)
    await send_email.defer_async(
        to=fake.email(),
        subject="Scheduled Email",
        body=fake.paragraph(nb_sentences=4),
    )


async def main() -> None:
    # Open Procrastinate for the whole lifetime of the scheduler process
    async with procrastinate_app.open_async():
        scheduler = AsyncIOScheduler()

        # Smoke/health task every minute
        scheduler.add_job(
            enqueue_ping,
            IntervalTrigger(minutes=1),
            id="ping",
            replace_existing=True,
        )

        # Every 2 minutes at second 0
        scheduler.add_job(
            enqueue_send_email,  # plain coroutine function — no lambda
            CronTrigger(second=0, minute="*/2"),
            id="send-email",
            replace_existing=True,
        )

        # Optional:
        # scheduler.add_job(
        #     enqueue_poll_provider,
        #     IntervalTrigger(seconds=30),
        #     id="poll-provider",
        #     replace_existing=True,
        # )
        # scheduler.add_job(
        #     enqueue_dispatch_due_work,
        #     IntervalTrigger(minutes=5),
        #     id="dispatch-due-work",
        #     replace_existing=True,
        # )

        scheduler.start()
        print("Scheduler started. Press Ctrl+C to exit.")
        try:
            await asyncio.Event().wait()  # run forever
        finally:
            scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())