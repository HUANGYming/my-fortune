from datetime import datetime, time
from lunar_python.util import LunarUtil
from app.calculations.almanac import calculate_almanac
from app.calculations.bazi import LABELS, birth_context, fortune_cycles, render_bazi
from app.calculations.calendar import CALENDAR_ZONE, resolve_instant, solar
from app.calculations.relations import analyze, fortune_hints, tai_sui


def calculate_context(patron, target_date) -> dict:
    if patron.birth_date and target_date < patron.birth_date:
        raise ValueError('Fortune date precedes birth date')
    pairs = {}
    bazi = None
    status = 'general'
    terms = late_terms = None
    if patron.birth_date and patron.gender and patron.birth_timezone:
        pairs, local, terms, late_terms, correction = birth_context(patron)
        bazi = render_bazi(patron, pairs, local, correction)
        status = 'three_pillars' if patron.birth_hour is None else 'four_pillars'
    master = pairs['day'][0] if pairs else None
    almanac, daily = calculate_almanac(target_date, master)
    day = daily.getEightChar().getDay()
    natal = [{"label": label, "stem": pair[0], "branch": pair[1]} for label,pair in pairs.items()]
    relations = None
    if pairs:
        # Seasonal year/month are resolved at local noon, matching TaiBu day selector.
        noon = datetime.combine(target_date, time(12))
        flow = solar(resolve_instant(noon, 'Asia/Macau').astimezone(CALENDAR_ZONE)).getLunar()
        flow_year = flow.getYearInGanZhiExact()
        effective_year = target_date.year if flow_year == LunarUtil.JIA_ZI[(target_date.year - 4) % 60] else target_date.year - 1
        overlay, cycles = fortune_cycles(patron, terms, late_terms, effective_year)
        overlay.extend({"label":label, "stem":pair[0], "branch":pair[1]} for label,pair in (
            ('流年',flow_year),('流月',flow.getMonthInGanZhiExact()),('流日',day)))
        pillars = [{**p, 'label':LABELS[p['label']]} for p in natal] + overlay
        relations = {"参与柱":pillars, "干支关系":analyze(pillars,len(natal)), "大运":cycles,
                     "原局关系":analyze(pillars[:len(natal)]),
                     "岁运提示":fortune_hints(pillars,len(natal)),
                     "太岁关系":tai_sui(flow_year[1],pairs["year"][1]),
                     "计算规则":{"ruleVersion":"python-relations-v1"}}
    return {"engine":{"name":"my-fortune-python", "version":"1.0.0", "upstream":"taibu-core 4.1.0 / 4b2a51a",
                      "calendar":"lunar-python 1.4.9", "astronomy":"astronomy-engine 2.1.19"},
            "personalization":status, "almanac":almanac,"bazi":bazi,"relations":relations,
            "coordinates":{"day_stem":day[0],"day_branch":day[1],"day_master":master,"natal":natal}}
