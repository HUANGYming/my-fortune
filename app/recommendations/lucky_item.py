from pydantic import Field
from app.llm import QwenClient
from app.models import CatalogEntry, StrictModel
from app.rules import rank_catalog


class Selection(StrictModel):
    entry_id: str
    reason: str = Field(min_length=1, max_length=1000)


async def generate(llm: QwenClient, context: dict, catalog: list[CatalogEntry]) -> CatalogEntry:
    ranked = rank_catalog(context, catalog, "item")[:20]
    selection_context = {
        **context,
        "candidates": [{**entry.model_dump(), "rule_score": score} for score, entry in ranked],
    }
    result = await llm.generate(
        "Choose one item from candidates using the daily reading, theme color and patron "
        "preferences. Rule scores are supporting context. Return its exact entry_id and "
        "a concise reason grounded in supplied facts. Select only a listed candidate.",
        selection_context, Selection,
    )
    for _, entry in ranked:
        if entry.id == result.entry_id:
            context.setdefault("catalog_decisions", {})["item"] = result.model_dump()
            return entry
    raise ValueError("Qwen selected a item outside the eligible candidates")
