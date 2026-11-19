from datetime import date, datetime, timezone
from app.config import Settings
from app.llm import QwenClient
from app.models import Fortune, Patron
from app.repository import Repository
from app.taibu import TaibuClient
from app.rules import DailyReading, RULES_VERSION, theme_candidates
from app.recommendations import lucky_zodiac, lucky_number, lucky_color, lucky_item, lucky_dining


class FortuneService:
    def __init__(self, settings: Settings, repository: Repository):
        self.settings = settings
        self.repository = repository
        self.llm = QwenClient(settings)
        self.taibu = TaibuClient(settings)

    async def generate(self, patron: Patron, target_date: date) -> Fortune:
        existing = self.repository.get_fortune(patron.patron_id, target_date)
        if existing:
            return existing
        item_catalog = self.repository.catalog("item")
        dining_catalog = self.repository.catalog("dining")
        if not item_catalog or not dining_catalog:
            raise ValueError("Both item and dining catalogs require active entries")
        facts = await self.taibu.context(patron, target_date)
        # Patron ID is a storage key, not an input to the model.
        profile = patron.model_dump(mode="json", exclude={"patron_id"})
        profile["preferences"].pop("preferred_colors", None)
        context = {"date": target_date.isoformat(), "profile": profile, "facts": facts}
        context["theme_candidates"] = theme_candidates(facts)
        reading = await self.llm.generate(
            "Select one element from theme_candidates after considering personal day-master, "
            "daily almanac, and the supplied natal/day relation facts. Scores are editorial "
            "support weights, not classical strength or useful-god conclusions. "
            "Use only supplied facts for basis. Return a concise daily theme.", context, DailyReading,
        )
        if reading.element not in {candidate["element"] for candidate in context["theme_candidates"]}:
            raise ValueError("Qwen selected an element outside the rule candidates")
        context["daily_reading"] = reading.model_dump()
        zodiac = lucky_zodiac.generate(context)
        number = lucky_number.generate(context)
        color = lucky_color.generate(context)
        context["lucky_color"] = color.model_dump()
        item = await lucky_item.generate(self.llm, context, item_catalog)
        context["selected_item"] = item.model_dump()
        dining = await lucky_dining.generate(self.llm, context, dining_catalog)
        fortune = Fortune(
            patron_id=patron.patron_id, fortune_date=target_date,
            lucky_zodiac=zodiac, lucky_number=number, lucky_color=color,
            lucky_item=item, lucky_dining=dining, generated_at=datetime.now(timezone.utc),
            model=self.settings.qwen_model, prompt_version=self.settings.prompt_version,
            rules_version=RULES_VERSION, personalization=facts["personalization"],
        )
        self.repository.save(fortune, {"facts": facts, "reading": reading.model_dump(), "rules_version": RULES_VERSION,
                                     "theme_candidates": context["theme_candidates"],
                                     "catalog_decisions": context["catalog_decisions"]})
        # A concurrent publisher may have won. Return the canonical persisted result.
        saved = self.repository.get_fortune(patron.patron_id, target_date)
        if saved is None:
            raise RuntimeError("Published fortune could not be read")
        return saved
