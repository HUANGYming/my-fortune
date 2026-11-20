"""Versioned editorial rules for daily entertainment recommendations."""
from datetime import date
from app.models import CatalogEntry

RULES_VERSION = "daily-theme-v8"
ELEMENTS = ("wood", "fire", "earth", "metal", "water")
STEM_ELEMENTS = dict(zip("甲乙丙丁戊己庚辛壬癸", (
    "wood", "wood", "fire", "fire", "earth", "earth", "metal", "metal", "water", "water")))
# Generating cycle: wood -> fire -> earth -> metal -> water -> wood.
GENERATES = dict(zip(ELEMENTS, ("fire", "earth", "metal", "water", "wood")))
GENERATED_BY = {child: parent for parent, child in GENERATES.items()}
# Controlling cycle: wood -> earth -> water -> fire -> metal -> wood.
CONTROLS = dict(zip(ELEMENTS, ("earth", "metal", "water", "wood", "fire")))
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
# Zodiac names follow the same order as the twelve earthly branches above.
ZODIACS = ("Rat", "Ox", "Tiger", "Rabbit", "Dragon", "Snake", "Horse", "Goat", "Monkey", "Rooster", "Dog", "Pig")
COMBINES = ("子丑", "寅亥", "卯戌", "辰酉", "巳申", "午未")
TRINES = ("申子辰", "亥卯未", "寅午戌", "巳酉丑")
CLASHES = ("子午", "丑未", "寅申", "卯酉", "辰戌", "巳亥")


def daily_element_decision(facts: dict) -> dict:
    """Choose a support element from the daily stem and natal day master.

    Generating, draining, or controlling days use the element that generates the master.
    Same-element days or days controlled by the master use the master's own element.
    This product policy does not assess chart strength or favorable elements.
    """
    coords = facts["coordinates"]
    daily = STEM_ELEMENTS[coords["day_stem"]]
    master = coords.get("day_master")
    if master is None:
        # Without a natal chart, use a general daily theme instead of inventing one.
        return {
            "strategy": "general", "day_master_element": None,
            "day_element": daily, "relationship": None, "element": daily,
            "reason": "缺少个人日主，使用当天日干五行作为一般主题，不作个人生扶判断。",
        }

    personal = STEM_ELEMENTS[master]
    parent = GENERATED_BY[personal]
    if daily == personal:
        relationship, element = "same", personal
        reason = "当天五行与日主同类，采用同类五行帮助日主。"
    elif GENERATES[daily] == personal:
        relationship, element = "generates_master", parent
        reason = "当天五行生助日主，采用生我五行延续生助方向。"
    elif GENERATES[personal] == daily:
        relationship, element = "generated_by_master", parent
        reason = "日主生当天五行，形成泄；采用生我五行补充支持。"
    elif CONTROLS[personal] == daily:
        relationship, element = "controlled_by_master", personal
        reason = "日主克当天五行，形成消耗；采用同类五行帮助日主。"
    else:
        relationship, element = "controls_master", parent
        reason = "当天五行克日主，采用“当天五行→生我五行→日主”的相生链条作为缓和方向。"
    return {
        "strategy": "support", "day_master_element": personal,
        "day_element": daily, "relationship": relationship,
        "element": element, "reason": reason,
    }


def catalog_matches(context: dict, entry: CatalogEntry) -> dict[str, bool]:
    """Validate current catalog tags without changing historical payload parsing."""
    tags = {}
    for key, allowed in (("elements", ELEMENTS), ("zodiacs", ZODIACS), ("colors", None)):
        # Require arrays so a string such as "metal" cannot match as a substring.
        values = entry.metadata.get(key, [])
        if (not isinstance(values, list)
                or any(not isinstance(value, str) or (allowed is not None and value not in allowed)
                       for value in values)):
            raise ValueError(f"Invalid {key} tags for catalog entry {entry.id}")
        tags[key] = values
    return {
        "element": context["daily_reading"]["element"] in tags["elements"],
        "zodiac": context.get("lucky_zodiac") in tags["zodiacs"],
        "color": context["lucky_color"]["name"].casefold() in
                 [value.casefold() for value in tags["colors"]],
    }


def rank_catalog(context: dict, catalog: list[CatalogEntry], kind: str) -> list[CatalogEntry]:
    """Require the daily element; prefer zodiac, then color, then stable ID order."""
    element = context["daily_reading"]["element"]
    candidates = []
    for entry in catalog:
        matches = catalog_matches(context, entry)
        if matches["element"]:
            # Zodiac and color never make a wrong-element entry eligible.
            candidates.append((matches, entry))
    if not candidates:
        raise ValueError(f"No eligible {kind} candidate for element {element}")
    # Boolean priority tiers avoid arbitrary numeric weights.
    candidates.sort(key=lambda candidate: (
        not candidate[0]["zodiac"], not candidate[0]["color"], candidate[1].id,
    ))
    return [entry for _, entry in candidates]


def select_catalog(context: dict, catalog: list[CatalogEntry], kind: str) -> CatalogEntry:
    """Deterministic fixture selection; production selection is performed by Qwen."""
    candidates = rank_catalog(context, catalog, kind)
    best = catalog_matches(context, candidates[0])
    tied = [entry for entry in candidates if catalog_matches(context, entry) == best]
    return tied[date.fromisoformat(context["date"]).toordinal() % len(tied)]
