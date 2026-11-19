import asyncio
from datetime import date
from app.models import Patron
from app.config import Settings
from app.calculations.engine import calculate_context


class TaibuClient:
    """Compatibility entry point for the native Python implementation."""

    def __init__(self, settings: Settings):
        self.settings = settings

    async def context(self, patron: Patron, target_date: date) -> dict:
        return await asyncio.to_thread(calculate_context, patron, target_date)
