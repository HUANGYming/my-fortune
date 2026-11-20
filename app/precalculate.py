"""Generate daily fortunes for all Patrons in the source table."""
import argparse
import asyncio
from datetime import date, datetime
import logging
from zoneinfo import ZoneInfo
from app.config import CONCURRENCY_LIMIT, get_settings
from app.repository import Repository
from app.service import FortuneService

logger = logging.getLogger(__name__)


async def run(target_date: date, batch_size: int = 500) -> int:
    """Process the full source table with bounded concurrency; return the failure count."""
    settings = get_settings()
    repo = Repository(settings)
    # Workers share one service and its Qwen request semaphore.
    service = FortuneService(settings, repo)
    failures = 0
    processed = 0
    queue = asyncio.Queue(maxsize=CONCURRENCY_LIMIT * 2)

    async def produce():
        # Advance the paginated synchronous iterator off the event loop.
        # Returning None avoids propagating StopIteration through an asyncio Future.
        patron_ids = iter(repo.iter_patron_ids(batch_size))
        while True:
            patron_id = await asyncio.to_thread(next, patron_ids, None)
            if patron_id is None:
                break
            await queue.put(patron_id)
        for _ in range(CONCURRENCY_LIMIT):
            # One sentinel lets each worker stop after all queued patrons are consumed.
            await queue.put(None)

    async def consume():
        nonlocal processed, failures
        while True:
            patron_id = await queue.get()
            if patron_id is None:
                return
            processed += 1
            try:
                patron = await asyncio.to_thread(repo.get_patron, patron_id)
                if patron is None:
                    raise ValueError("Patron not found")
                await service.generate(patron, target_date)
                logger.info("Fortune available for patron=%s date=%s", patron_id, target_date)
            except Exception:
                # A patron failure is logged without stopping the rest of the batch.
                failures += 1
                logger.exception("Generation failed for patron=%s date=%s", patron_id, target_date)

    # Bound both active work and queued IDs, even for millions of source Patrons.
    # TaskGroup cancels the batch if source pagination fails or the job is cancelled.
    async with asyncio.TaskGroup() as tasks:
        tasks.create_task(produce())
        for _ in range(CONCURRENCY_LIMIT):
            tasks.create_task(consume())
    logger.info("Batch finished date=%s processed=%s succeeded=%s failed=%s",
                target_date, processed, processed - failures, failures)
    return failures


def positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("Must be positive")
    return parsed


def main():
    # The target date follows Macau time, regardless of the server's timezone.
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat,
                        default=datetime.now(ZoneInfo("Asia/Macau")).date())
    parser.add_argument("--batch-size", type=positive_integer, default=500)
    args = parser.parse_args()
    raise SystemExit(1 if asyncio.run(run(args.date, args.batch_size)) else 0)


if __name__ == "__main__":
    main()
