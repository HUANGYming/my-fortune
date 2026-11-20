"""Versioned editorial rules for daily entertainment recommendations."""
from datetime import date
from app.models import CatalogEntry

RULES_VERSION = "daily-theme-v7"
ELEMENTS = ("wood", "fire", "earth", "metal", "water")
STEM_ELEMENTS = dict(zip("甲乙丙丁戊己庚辛壬癸", (
    "wood", "wood", "fire", "fire", "earth", "earth", "metal", "metal", "water", "water")))
# 相生关系：木生火、火生土、土生金、金生水、水生木。
GENERATES = dict(zip(ELEMENTS, ("fire", "earth", "metal", "water", "wood")))
GENERATED_BY = {child: parent for parent, child in GENERATES.items()}
# 相克关系：木克土、火克金、土克水、金克木、水克火。
CONTROLS = dict(zip(ELEMENTS, ("earth", "metal", "water", "wood", "fire")))
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
ZODIACS = ("Rat", "Ox", "Tiger", "Rabbit", "Dragon", "Snake", "Horse", "Goat", "Monkey", "Rooster", "Dog", "Pig")
COMBINES = ("子丑", "寅亥", "卯戌", "辰酉", "巳申", "午未")
TRINES = ("申子辰", "亥卯未", "寅午戌", "巳酉丑")
CLASHES = ("子午", "丑未", "寅申", "卯酉", "辰戌", "巳亥")


def daily_element_decision(facts: dict) -> dict:
    """Apply the agreed support policy, not a full 旺衰 / 喜用神 assessment.

    生我、我生、克我 -> 生我的五行；同我、我克 -> 日主五行。
    No random mode, element scores, or date-based tie-breaking are used.
    """
    coords = facts["coordinates"]
    daily = STEM_ELEMENTS[coords["day_stem"]]
    master = coords.get("day_master")
    if master is None:
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
