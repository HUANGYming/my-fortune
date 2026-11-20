"""Select a zodiac from personal branch partners and daily relations."""
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
    """Use stable earthly-branch order regardless of set or natal pillar order."""
    return [branch for branch in BRANCHES if branch in branches]


def generate(context: dict) -> Zodiac:
    """Return a zodiac and attach the full decision trace to the shared context."""
    coordinates = context["facts"]["coordinates"]
    daily = coordinates["day_branch"]
    clash = CLASH_PARTNER[daily]
    natal = [{"label": pillar["label"], "branch": pillar["branch"]}
             for pillar in coordinates.get("natal", [])
             if pillar["label"] in ("year", "month", "day", "hour")]

    # Deduplicate combine partners from known natal pillars; unknown hours are skipped.
    sources = [{**pillar, "candidate": COMBINE_PARTNER[pillar["branch"]]}
               for pillar in natal]
    source = "personal_combines" if natal else "daily_combine"
    base = {entry["candidate"] for entry in sources} if natal else {COMBINE_PARTNER[daily]}
    eligible = base - {clash}
    fallback: set[str] = set()
    if not eligible:
        # Expand personal trine-group partners only if every combine candidate clashes today.
        source = "personal_trines"
        fallback = {peer for pillar in natal for peer in TRINE_PARTNERS[pillar["branch"]]}
        eligible = fallback - {clash}
    if not eligible:
        raise ValueError("No eligible zodiac candidate after daily clash exclusion")

    # Daily combine and trine partners share priority; only today's clash is a hard veto.
    daily_partners = {COMBINE_PARTNER[daily], *TRINE_PARTNERS[daily]}
    preferred = eligible & daily_partners
    pool = _ordered(preferred or eligible)
    # Date-based rotation is reproducible and does not use random sampling.
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
    # service.py forwards this evidence to Qwen and persists it in audit_json.
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
