from datetime import datetime, time
from lunar_python.util import LunarUtil
from app.calculations.calendar import CALENDAR_ZONE, resolve_instant, solar, true_solar_time

LABELS = {"year": "年柱", "month": "月柱", "day": "日柱", "hour": "时柱"}


def ten_god(master: str, target: str) -> str:
    return LunarUtil.SHI_SHEN[master + target]


def birth_context(patron):
    unknown = patron.birth_hour is None
    wall = datetime.combine(patron.birth_date, time(patron.birth_hour or 0, 0 if unknown else patron.birth_minute or 0))
    instant = resolve_instant(wall, patron.birth_timezone, unknown_hour=unknown)
    terms = solar(instant.astimezone(CALENDAR_ZONE)).getLunar()
    late_terms = terms
    if unknown:
        late = datetime.combine(patron.birth_date, time(23, 59))
        late_terms = solar(resolve_instant(late, patron.birth_timezone, unknown_hour=True).astimezone(CALENDAR_ZONE)).getLunar()
        if (terms.getYearInGanZhiExact(), terms.getMonthInGanZhiExact()) != (late_terms.getYearInGanZhiExact(), late_terms.getMonthInGanZhiExact()):
            raise ValueError("Unknown birth hour on a solar-term boundary requires clarification")
    correction = None
    if patron.longitude is not None and not unknown:
        wall, correction = true_solar_time(instant, patron.birth_timezone, patron.longitude)
    local = solar(wall).getLunar().getEightChar()
    local.setSect(2)  # Midnight day boundary, matching the existing API contract.
    pairs = {"year": terms.getYearInGanZhiExact(), "month": terms.getMonthInGanZhiExact(),
             "day": local.getDay()}
    if not unknown:
        pairs["hour"] = local.getTime()
    return pairs, local, terms, late_terms, correction


def life_stage(master: str, branch: str) -> str:
    stems = "甲乙丙丁戊己庚辛壬癸"
    branches = "子丑寅卯辰巳午未申酉戌亥"
    start = dict(zip(stems, "亥午寅酉寅酉巳子申卯"))[master]
    direction = 1 if stems.index(master) % 2 == 0 else -1
    index = (direction * (branches.index(branch) - branches.index(start))) % 12
    return ("长生", "沐浴", "冠带", "临官", "帝旺", "衰", "病", "死", "墓", "绝", "胎", "养")[index]


def render_bazi(patron, pairs: dict, local, correction) -> dict:
    master = pairs['day'][0]
    pillars = []
    for label, pair in pairs.items():
        pillars.append({"柱": LABELS[label], "干支": pair,
                        "天干十神": '-' if label == 'day' else ten_god(master, pair[0]),
                        "藏干": [{"天干": stem, "十神": ten_god(master, stem)}
                                 for stem in LunarUtil.ZHI_HIDE_GAN[pair[1]]],
                        "地势": life_stage(master,pair[1]), "纳音": LunarUtil.NAYIN[pair]})
    basic = {"性别": '男' if patron.gender == 'male' else '女', "日主": master}
    if patron.birth_hour is None:
        basic['出生时辰'] = '未知'
    if correction:
        basic['真太阳时'] = correction
    return {"基本信息": basic, "四柱": pillars,
            "计算规则": {"timezone": patron.birth_timezone, "dayBoundary": "midnight",
                         "solarTermBasis": "instant", "ruleVersion": "python-bazi-v1"}}


def fortune_cycles(patron, terms, late_terms, target_year: int) -> tuple[list[dict], dict]:
    gender = 1 if patron.gender == 'male' else 0
    yuns = [calendar.getEightChar().getYun(gender, 1) for calendar in (terms, late_terms)]
    yuns.sort(key=lambda yun: yun.getStartSolar().toYmdHms())
    yun = yuns[0]
    periods = [period for period in yun.getDaYun(11) if period.getGanZhi()]
    active = next((period for period in periods if period.getStartYear() <= target_year <= period.getEndYear()), None)
    overlay = []
    if active:
        overlay.append({"label": "大运", "stem": active.getGanZhi()[0], "branch": active.getGanZhi()[1]})
    elif patron.birth_hour is not None and target_year < periods[0].getStartYear():
        pre = yun.getDaYun(1)[0]
        small = next((value for value in pre.getXiaoYun() if value.getYear() == target_year), None)
        if small:
            overlay.append({"label": "小运", "stem": small.getGanZhi()[0], "branch": small.getGanZhi()[1]})
    return overlay, {"起运时间": yun.getStartSolar().toYmdHms(),
                     "最晚起运时间": yuns[-1].getStartSolar().toYmdHms(),
                     "起运时间时区": "UTC+08:00", "顺逆": '顺' if yun.isForward() else '逆',
                     "出生时辰未知": patron.birth_hour is None,
                     "大运列表": [{"干支": value.getGanZhi(), "开始年": value.getStartYear(),
                                  "结束年": value.getEndYear()} for value in periods]}
