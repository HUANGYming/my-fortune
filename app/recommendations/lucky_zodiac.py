from datetime import date
from app.models import Zodiac
from app.rules import BRANCHES, ZODIACS, relation_score


def generate(context: dict) -> Zodiac:
    coordinates = context["facts"]["coordinates"]
    anchors = [(coordinates["day_branch"], 2)]
    anchors.extend((pillar["branch"], 1) for pillar in coordinates["natal"]
                   if pillar["label"] in ("year", "day"))
    scores = {branch: sum(weight * relation_score(branch, anchor) for anchor, weight in anchors)
              for branch in BRANCHES}
    # Exclude direct clashes with today's branch.
    eligible = [branch for branch in BRANCHES if relation_score(branch, coordinates["day_branch"]) >= 0]
    best = max(scores[branch] for branch in eligible)
    tied = [branch for branch in eligible if scores[branch] == best]
    chosen = tied[date.fromisoformat(context["date"]).toordinal() % len(tied)]
    return Zodiac(ZODIACS[BRANCHES.index(chosen)])
