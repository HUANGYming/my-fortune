"""Run from the deployment scheduler; each patron commits independently."""
import argparse
import asyncio
from datetime import date
import logging
from app.config import get_settings
from app.repository import Repository
from app.service import FortuneService

logger = logging.getLogger(__name__)


async def run(target_date: date, patron_ids: list[str]) -> int:
    settings = get_settings()
    repo = Repository(settings)
    service = FortuneService(settings, repo)
    failures = 0
    for patron_id in dict.fromkeys(patron_ids):
        try:
            patron = repo.get_patron(patron_id)
            if patron is None:
                raise ValueError("Patron not found")
            await service.generate(patron, target_date)
            logger.info("Fortune persisted for requested patron")
        except Exception:
            failures += 1
            logger.exception("Patron generation failed")
    return failures


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=date.fromisoformat, required=True)
    parser.add_argument("--patron-id", action="append", required=True)
    args = parser.parse_args()
    raise SystemExit(1 if asyncio.run(run(args.date, args.patron_id)) else 0)


if __name__ == "__main__":
    main()
