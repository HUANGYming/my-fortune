"""Python adaptation of TaiBu ganzhi-relations.ts (MIT, hhszzzz)."""
from itertools import combinations

PAIR_RULES = (
    ('天干五合', 'stem', ('甲己','乙庚','丙辛','丁壬','戊癸'), ('土','金','水','木','火')),
    ('天干相冲', 'stem', ('甲庚','乙辛','丙壬','丁癸'), ('',)*4),
    ('六合', 'branch', ('子丑','寅亥','卯戌','辰酉','巳申','午未'), ('土','木','火','金','水','土')),
    ('六冲', 'branch', ('子午','丑未','寅申','卯酉','辰戌','巳亥'), ('',)*6),
    ('相害', 'branch', ('子未','丑午','寅巳','卯辰','申亥','酉戌'), ('',)*6),
    ('相破', 'branch', ('子酉','丑辰','寅亥','卯午','巳申','未戌'), ('',)*6),
)
TRINES = (('申子辰','水局'),('巳酉丑','金局'),('寅午戌','火局'),('亥卯未','木局'))
MEETINGS = (('寅卯辰','木'),('巳午未','火'),('申酉戌','金'),('亥子丑','水'))
HALVES = (('申子','辰','水'),('子辰','申','水'),('亥卯','未','木'),('卯未','亥','木'),
          ('寅午','戌','火'),('午戌','寅','火'),('巳酉','丑','金'),('酉丑','巳','金'))
PUNISHMENTS = (('寅巳申','无恩之刑'),('丑戌未','恃势之刑'),('子卯','无礼之刑'),
               ('辰','辰自刑'),('午','午自刑'),('酉','酉自刑'),('亥','亥自刑'))


def analyze(pillars: list[dict], natal_count: int = 0) -> list[dict]:
    focus = set(range(natal_count, len(pillars)))
    facts = {}

    def add(kind, part, indices, result=''):
        chars = ''.join(sorted({pillars[i][part] for i in indices}))
        anchors = tuple(sorted(focus.intersection(indices)))
        key = (kind, result, tuple(sorted(indices))) if kind not in ('三合','半合','三会','相刑') else (kind,result,chars,anchors)
        facts.setdefault(key, {"类型":kind, "结果":result,
            "位置":[{"柱":pillars[i]['label'], "部位": '天干' if part == 'stem' else '地支',
                    "字":pillars[i][part]} for i in indices]})

    for i,j in combinations(range(len(pillars)),2):
        if i not in focus and j not in focus:
            continue
        for kind,part,pairs,results in PAIR_RULES:
            a,b = pillars[i][part], pillars[j][part]
            for pair,result in zip(pairs,results):
                if a != b and set((a,b)) == set(pair):
                    add(kind,part,[i,j],result)
    all_branches = {p['branch'] for p in pillars}
    if natal_count == 0:
        for kind, groups in (("三合", TRINES), ("三会", MEETINGS)):
            for members, result in groups:
                if set(members).issubset(all_branches):
                    add(kind, "branch", [i for i, p in enumerate(pillars) if p['branch'] in members], result)
        for pair, missing, result in HALVES:
            if set(pair).issubset(all_branches) and missing not in all_branches:
                add("半合", "branch", [i for i, p in enumerate(pillars) if p['branch'] in pair], result)
        for members, result in PUNISHMENTS:
            indices = [i for i, p in enumerate(pillars) if p['branch'] in members]
            qualifies = len(indices) >= 2 if len(members) == 1 else len(set(members) & all_branches) >= 2
            if qualifies:
                add("相刑", "branch", indices, result)
        return list(facts.values())
    for target in sorted(focus):
        branch = pillars[target]['branch']
        for kind, groups in (('三合',TRINES),('三会',MEETINGS)):
            for members,result in groups:
                rest = set(members) - {branch}
                indices = [i for i,p in enumerate(pillars) if i != target and p['branch'] in rest]
                if branch in members and {pillars[i]['branch'] for i in indices} == rest:
                    add(kind,'branch',[target,*indices],result)
        for pair,missing,result in HALVES:
            if branch in pair and missing not in all_branches:
                indices = [i for i,p in enumerate(pillars) if i != target and p['branch'] in set(pair)-{branch}]
                if indices:
                    add('半合','branch',[target,*indices],result)
        for members,result in PUNISHMENTS:
            if branch in members:
                needed = set(members)-{branch} if len(members)>1 else {branch}
                indices = [i for i,p in enumerate(pillars) if i != target and p['branch'] in needed]
                if indices:
                    add('相刑','branch',[target,*indices],result)
    return list(facts.values())


def fortune_hints(pillars: list[dict], natal_count: int) -> list[str]:
    hints = []
    for i in range(natal_count, len(pillars)):
        b = pillars[i]
        for a in pillars[:i]:
            if (a['stem'],a['branch']) == (b['stem'],b['branch']):
                if a['label'] == '大运' and b['label'] == '流年':
                    hints.append(f"岁运并临（大运与流年同为{b['stem']}{b['branch']}）")
                else:
                    hints.append(f"{b['label']}伏吟{a['label']}（同为{b['stem']}{b['branch']}）")
            elif any(set((a['stem'],b['stem'])) == set(pair) for pair in PAIR_RULES[1][2]) and any(
                    set((a['branch'],b['branch'])) == set(pair) for pair in PAIR_RULES[3][2]):
                hints.append(f"{b['label']}与{a['label']}天克地冲（{b['stem']}{b['branch']}对{a['stem']}{a['branch']}，亦称反吟）")
    return hints


def tai_sui(year_branch: str, natal_branch: str) -> list[str]:
    result = ['值太岁'] if year_branch == natal_branch else []
    for name, pairs in (('冲太岁',PAIR_RULES[3][2]),('合太岁',PAIR_RULES[2][2])):
        if year_branch != natal_branch and any(set((year_branch,natal_branch)) == set(pair) for pair in pairs):
            result.append(name)
    if any(year_branch in members and natal_branch in members and
           (year_branch != natal_branch or len(members) == 1) for members,_ in PUNISHMENTS):
        result.append('刑太岁')
    for name,pairs in (('害太岁',PAIR_RULES[4][2]),('破太岁',PAIR_RULES[5][2])):
        if year_branch != natal_branch and any(set((year_branch,natal_branch)) == set(pair) for pair in pairs):
            result.append(name)
    return result
