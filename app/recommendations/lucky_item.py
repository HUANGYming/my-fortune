from pydantic import Field
from app.llm import QwenClient
from app.models import CatalogEntry, StrictModel
from app.rules import rank_catalog, catalog_matches


class Selection(StrictModel):
    entry_id: str
    reason: str = Field(min_length=1, max_length=1000)


async def generate(llm: QwenClient, context: dict, catalog: list[CatalogEntry]) -> CatalogEntry:
    ranked = rank_catalog(context, catalog, "item")[:20]
    selection_context = {
        **context,
        "candidates": [{**entry.model_dump(), "rule_matches": catalog_matches(context, entry)}
                       for entry in ranked],
    }
    result = await llm.generate(
        "Choose one item from candidates. All candidates match the required daily element. "
        "Prefer matching lucky_zodiac tags when available; zodiac tags are optional. "
        "Use the theme color, item descriptions and supplied facts to make the final choice. "
        "Do not infer preferences or claim improved gambling odds. Return its exact entry_id and "
        "a concise reason grounded in supplied facts. Select only a listed candidate.",
        selection_context, Selection,
    )
    for entry in ranked:
        if entry.id == result.entry_id:
            matches = catalog_matches(context, entry)
            context.setdefault("catalog_decisions", {})["item"] = {
                **result.model_dump(), "required_element": context["daily_reading"]["element"],
                "lucky_zodiac": context.get("lucky_zodiac"),
                "candidate_ids": [candidate.id for candidate in ranked],
                "rule_matches": matches,
                "matched_tags": {
                    "elements": [context["daily_reading"]["element"]],
                    "zodiacs": [context["lucky_zodiac"]] if matches["zodiac"] else [],
                    "colors": [context["lucky_color"]["name"]] if matches["color"] else [],
                },
            }
            return entry
    raise ValueError("Qwen selected an item outside the eligible candidates")
