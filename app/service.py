"""Coordinate calculation, five recommendations, and atomic publication."""
import asyncio
from datetime import date, datetime, timezone
from app.config import Settings
from app.llm import QwenClient
from app.models import Fortune, Patron
from app.repository import Repository
from app.taibu import TaibuClient
from app.rules import RULES_VERSION, daily_element_decision
from app.recommendations import lucky_zodiac, lucky_number, lucky_color, lucky_item, lucky_dining


class FortuneService:
    def __init__(self, settings: Settings, repository: Repository):
        self.settings = settings
        self.repository = repository
        self.llm = QwenClient(settings)
        self.taibu = TaibuClient(settings)

    async def generate(self, patron: Patron, target_date: date) -> Fortune:
        """Return an existing result or generate and persist all five fields."""
        # Step 1: Reuse a published result so batch retries do not overwrite it.
        existing = await asyncio.to_thread(self.repository.get_fortune, patron.patron_id, target_date)
        if existing:
            return existing

        # Step 2: Load active catalog entries; both kinds are required.
        item_catalog = await asyncio.to_thread(self.repository.catalog, "item")
        dining_catalog = await asyncio.to_thread(self.repository.catalog, "dining")
        if not item_catalog or not dining_catalog:
            raise ValueError("Both item and dining catalogs require active entries")

        # Step 3: Calculate natal, almanac, and luck-cycle facts in Python.
        # Missing birth data produces general daily facts; charts are not cached yet.
        facts = await self.taibu.context(patron, target_date)

        # Step 4: Share birth data, target date, and facts across recommendation modules.
        # Patron ID is a storage key and is excluded from model input.
        profile = patron.model_dump(mode="json", exclude={"patron_id"})
        context = {"date": target_date.isoformat(), "profile": profile, "facts": facts}

        # Step 5: Apply the support policy to the daily stem and natal day master.
        # The decision includes its inputs, relationship, and reason for model/audit use.
        context["element_decision"] = daily_element_decision(facts)

        # Step 6: Share the chosen element with number, color, and catalog rules.
        # This decision uses neither random sampling nor element scores.
        element = context["element_decision"]["element"]
        context["daily_reading"] = {"element": element}

        # Step 7: Generate zodiac from branch relations; number/color use the element.
        # The zodiac module also records its candidate trace in zodiac_decision.
        # Selected zodiac and color become optional catalog ranking signals.
        zodiac = lucky_zodiac.generate(context)
        number = lucky_number.generate(context)
        color = lucky_color.generate(context)
        context["lucky_color"] = color.model_dump()
        context["lucky_zodiac"] = zodiac.value

        # Step 8: Each module filters by element, ranks tags, and sends up to 20 IDs to Qwen.
        # Independent contexts allow concurrent item/dining calls without shared audit writes.
        # The shared client caps in-flight requests at 16; empty candidate pools fail.
        item_context = {**context, "catalog_decisions": {}}
        dining_context = {**context, "catalog_decisions": {}}
        async with asyncio.TaskGroup() as tasks:
            item_task = tasks.create_task(lucky_item.generate(self.llm, item_context, item_catalog))
            dining_task = tasks.create_task(lucky_dining.generate(self.llm, dining_context, dining_catalog))
        item = item_task.result()
        dining = dining_task.result()
        context["catalog_decisions"] = {
            **item_context["catalog_decisions"], **dining_context["catalog_decisions"],
        }

        # Step 9: Publish all five fields and audit evidence in one transaction.
        # Any earlier failure leaves no partially published fortune.
        fortune = Fortune(
            patron_id=patron.patron_id, fortune_date=target_date,
            lucky_zodiac=zodiac, lucky_number=number, lucky_color=color,
            lucky_item=item, lucky_dining=dining, generated_at=datetime.now(timezone.utc),
            model=self.settings.qwen_model, prompt_version=self.settings.prompt_version,
            rules_version=RULES_VERSION, personalization=facts["personalization"],
        )
        await asyncio.to_thread(self.repository.save, fortune, {"facts": facts, "reading": {"element": element}, "rules_version": RULES_VERSION,
                                     "element_decision": context["element_decision"],
                                     "zodiac_decision": context["zodiac_decision"],
                                     "catalog_decisions": context["catalog_decisions"]})

        # Step 10: Return the stored document, including any result published by a rival worker.
        saved = await asyncio.to_thread(self.repository.get_fortune, patron.patron_id, target_date)
        if saved is None:
            raise RuntimeError("Published fortune could not be read")
        return saved
