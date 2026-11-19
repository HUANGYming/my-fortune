"""Versioned editorial rules for daily entertainment recommendations."""
from datetime import date
from typing import Literal
from pydantic import Field
from app.models import CatalogEntry, StrictModel

RULES_VERSION = "daily-theme-v3"
Element = Literal["wood", "fire", "earth", "metal", "water"]
ELEMENTS = ("wood", "fire", "earth", "metal", "water")
STEM_ELEMENTS = dict(zip("甲乙丙丁戊己庚辛壬癸", (
    "wood", "wood", "fire", "fire", "earth", "earth", "metal", "metal", "water", "water")))
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
ZODIACS = ("Rat", "Ox", "Tiger", "Rabbit", "Dragon", "Snake", "Horse", "Goat", "Monkey", "Rooster", "Dog", "Pig")
COMBINES = ("子丑", "寅亥", "卯戌", "辰酉", "巳申", "午未")
TRINES = ("申子辰", "亥卯未", "寅午戌", "巳酉丑")
CLASHES = ("子午", "丑未", "寅申", "卯酉", "辰戌", "巳亥")


class DailyReading(StrictModel):
    element: Element
    theme: str = Field(min_length=1, max_length=500)
    basis: list[str] = Field(min_length=1, max_length=10)


def theme_candidates(facts: dict) -> list[dict]:
    coords = facts["coordinates"]
    daily = STEM_ELEMENTS[coords["day_stem"]]
    scores = {element: 0 for element in ELEMENTS}
    scores[daily] += 2
    master = coords.get("day_master")
    if master:
        personal = STEM_ELEMENTS[master]
        scores[personal] += 2
        # Generating predecessor supports the day-master in this editorial method.
        scores[ELEMENTS[(ELEMENTS.index(personal) - 1) % 5]] += 1
    ordered = sorted(ELEMENTS, key=lambda element: (-scores[element], ELEMENTS.index(element)))
    return [{"element": element, "score": scores[element]} for element in ordered if scores[element] > 0]


def relation_score(candidate: str, branch: str) -> int:
    if candidate != branch and any(candidate in pair and branch in pair for pair in CLASHES):
        return -4
    if candidate != branch and any(candidate in pair and branch in pair for pair in COMBINES):
        return 3
    if candidate != branch and any(candidate in group and branch in group for group in TRINES):
        return 2
    return 0


def rank_catalog(context: dict, catalog: list[CatalogEntry], kind: str) -> list[tuple[int, CatalogEntry]]:
    element = context["daily_reading"]["element"]
    color = context["lucky_color"]["name"].lower()
    candidates = []
    for entry in catalog:
        tags = entry.metadata
        score = 5 * (element in tags.get("elements", []))
        score += 2 * (color in [value.lower() for value in tags.get("colors", [])])
        candidates.append((score, entry))
    if not candidates:
        raise ValueError(f"No eligible {kind} candidate")
    candidates.sort(key=lambda candidate: (-candidate[0], candidate[1].id))
    return candidates


def select_catalog(context: dict, catalog: list[CatalogEntry], kind: str) -> CatalogEntry:
    """Deterministic fixture selection; production selection is performed by Qwen."""
    candidates = rank_catalog(context, catalog, kind)
    best = candidates[0][0]
    tied = [entry for score, entry in candidates if score == best]
    return tied[date.fromisoformat(context["date"]).toordinal() % len(tied)]
