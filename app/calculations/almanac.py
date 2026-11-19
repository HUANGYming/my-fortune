from datetime import datetime, time
from app.calculations.calendar import solar
from app.calculations.bazi import ten_god


def calculate_almanac(target_date, master: str | None) -> tuple[dict, object]:
    lunar = solar(datetime.combine(target_date, time())).getLunar()
    day = lunar.getEightChar().getDay()
    basic = {"日期": target_date.isoformat(), "日干支": day}
    if master:
        basic["流日十神"] = ten_god(master, day[0])
    nine = lunar.getDayNineStar()
    return {
        "基础与个性化坐标": basic,
        "传统黄历基调": {"农历": lunar.toString(), "生肖": lunar.getYearShengXiao(),
                       "冲煞": '冲' + lunar.getDayChongDesc() + ' 煞' + lunar.getDaySha(),
                       "节气": lunar.getJieQi(),
                       "彭祖百忌": lunar.getPengZuGan() + ' ' + lunar.getPengZuZhi(),
                       "胎神占方": lunar.getDayPositionTai(),
                       "日九星": {"描述": nine.toFullString(), "方位": nine.getPositionDesc()}},
        "择日宜忌": {"宜": lunar.getDayYi(), "忌": lunar.getDayJi()},
        "神煞参考": {"吉神宜趋": lunar.getDayJiShen(), "凶煞宜忌": lunar.getDayXiongSha()},
        "计算规则": {"timezone": "Asia/Macau", "ruleVersion": "python-almanac-v1"},
    }, lunar
