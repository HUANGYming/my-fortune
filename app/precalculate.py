"""Generate daily fortunes for all Patrons in the source table."""
import argparse
import asyncio
from datetime import date, datetime
import logging
from zoneinfo import ZoneInfo
from app.config import get_settings
from app.repository import Repository
from app.service import FortuneService

logger = logging.getLogger(__name__)


async def run(target_date: date, batch_size: int = 500) -> int:
    settings = get_settings()
    repo = Repository(settings)
    service = FortuneService(settings, repo)
    failures = 0
    processed = 0
    for patron_id in repo.iter_patron_ids(batch_size):
        processed += 1
        try:
            patron = repo.get_patron(patron_id)
            if patron is None:
                raise ValueError("Patron not found")
            await service.generate(patron, target_date)
            logger.info("Fortune available for patron=%s date=%s", patron_id, target_date)
        except Exception:
            failures += 1
            logger.exception("Generation failed for patron=%s date=%s", patron_id, target_date)
    logger.info("Batch finished date=%s processed=%s succeeded=%s failed=%s",
                target_date, processed, processed - failures, failures)
    return failures


def positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("Must be positive")
    return parsed


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat,
                        default=datetime.now(ZoneInfo("Asia/Macau")).date())
    parser.add_argument("--batch-size", type=positive_integer, default=500)
    args = parser.parse_args()
    raise SystemExit(1 if asyncio.run(run(args.date, args.batch_size)) else 0)


if __name__ == "__main__":
    main()
