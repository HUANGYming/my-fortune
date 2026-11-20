from datetime import date
from app.models import Zodiac
from app.rules import BRANCHES, ZODIACS, COMBINES, TRINES, CLASHES

COMBINE_PARTNER = {
    branch: partner for left, right in COMBINES
    for branch, partner in ((left, right), (right, left))
}
CLASH_PARTNER = {
    branch: partner for left, right in CLASHES
    for branch, partner in ((left, right), (right, left))
}
TRINE_PARTNERS = {
    branch: tuple(peer for peer in group if peer != branch)
    for group in TRINES for branch in group
}


def _ordered(branches: set[str]) -> list[str]:
    """Use a stable 十二地支 order, independent of set or natal pillar order."""
    return [branch for branch in BRANCHES if branch in branches]


def generate(context: dict) -> Zodiac:
    coordinates = context["facts"]["coordinates"]
    daily = coordinates["day_branch"]
    clash = CLASH_PARTNER[daily]
    natal = [{"label": pillar["label"], "branch": pillar["branch"]}
             for pillar in coordinates.get("natal", [])
             if pillar["label"] in ("year", "month", "day", "hour")]

    # 个人四支各取六合，合并去重；未知时辰不会补造时支。
    sources = [{**pillar, "candidate": COMBINE_PARTNER[pillar["branch"]]}
               for pillar in natal]
    source = "personal_combines" if natal else "daily_combine"
    base = {entry["candidate"] for entry in sources} if natal else {COMBINE_PARTNER[daily]}
    eligible = base - {clash}
    fallback: set[str] = set()
    if not eligible:
        # 仅在个人六合候选全部与当天六冲时，扩展个人三合组伙伴。
        source = "personal_trines"
        fallback = {peer for pillar in natal for peer in TRINE_PARTNERS[pillar["branch"]]}
        eligible = fallback - {clash}
    if not eligible:
        raise ValueError("No eligible zodiac candidate after daily clash exclusion")

    # 当天六合与同组三合为同一优先级；不另设六合必胜或个人四支冲突否决。
    daily_partners = {COMBINE_PARTNER[daily], *TRINE_PARTNERS[daily]}
    preferred = eligible & daily_partners
    pool = _ordered(preferred or eligible)
    index = date.fromisoformat(context["date"]).toordinal() % len(pool)
    chosen = pool[index]
    zodiac = Zodiac(ZODIACS[BRANCHES.index(chosen)])
    if chosen == COMBINE_PARTNER[daily]:
        daily_relation = "combine"
    elif chosen in TRINE_PARTNERS[daily]:
        daily_relation = "trine_group"
    else:
        daily_relation = "neutral"

    if source == "daily_combine":
        reason = "缺少个人地支，使用当天六合生肖作为一般主题。"
    else:
        origin = "个人四支的六合生肖" if source == "personal_combines" else "个人六合候选全部被排除后扩展的三合组伙伴"
        priority = "优先选择与当天六合或同属三合组的候选" if preferred else "候选均无当天六合或同组三合关系，使用剩余无冲候选"
        reason = f"从{origin}出发，排除与当天{daily}六冲的{clash}；{priority}，按目标日期在固定地支顺序中选择{chosen}（{zodiac.value}）。"
    context["zodiac_decision"] = {
        "candidate_source": source, "day_branch": daily,
        "personal_branches": natal, "candidate_origins": sources,
        "base_candidates": _ordered(base), "base_excluded": _ordered(base & {clash}),
        "fallback_candidates": _ordered(fallback),
        "fallback_excluded": _ordered(fallback & {clash}),
        "eligible_candidates": _ordered(eligible), "preferred_candidates": _ordered(preferred),
        "selection_pool": pool, "rotation_index": index,
        "daily_relationship": daily_relation, "selected_branch": chosen,
        "zodiac": zodiac.value, "reason": reason,
    }
    return zodiac
