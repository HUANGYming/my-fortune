import json
from datetime import date
from pathlib import Path
import pytest
from app.models import Patron
from app.calculations.engine import calculate_context
from app.calculations.calendar import resolve_instant
from datetime import datetime

CASES = json.loads((Path(__file__).parent / 'fixtures/taibu_reference.json').read_text())


def normalize_relations(rows):
    return {(row['类型'], row.get('结果',''), tuple(sorted(
        (cell['柱'],cell['部位'],cell['字']) for cell in row['位置']))) for row in rows}


@pytest.mark.parametrize('case', CASES, ids=[str(i) for i in range(len(CASES))])
def test_native_python_matches_captured_taibu(case):
    payload = case['input']
    actual = calculate_context(Patron(patron_id='REF', **payload['patron']),date.fromisoformat(payload['date']))
    expected = case['expected']
    assert actual['coordinates'] == expected['coordinates']
    assert actual['personalization'] == expected['personalization']
    assert [(p['干支'],p['天干十神'],p['藏干']) for p in actual['bazi']['四柱']] == [
        (p['干支'],p['天干十神'],p['藏干']) for p in expected['bazi']['四柱']]
    assert [p['地势'] for p in actual['bazi']['四柱']] == [p['地势'] for p in expected['bazi']['四柱']]
    traditional = {key:value for key,value in actual['almanac']['传统黄历基调'].items() if value}
    assert traditional == expected['almanac']['传统黄历基调']
    for section in ('基础与个性化坐标','择日宜忌','神煞参考'):
        assert actual['almanac'][section] == expected['almanac'][section]
    assert [(p['label'],p['stem']+p['branch']) for p in actual['relations']['参与柱']] == [
        (p['柱'],p['干支']) for p in expected['relations']['参与柱位']]
    assert actual['relations']['岁运提示'] == expected['relations'].get('岁运提示',[])
    assert actual['relations']['太岁关系'] == expected['relations'].get('太岁关系',[])
    assert normalize_relations(actual['relations']['干支关系']) == normalize_relations(expected['relations']['叠加关系'])


@pytest.mark.parametrize('wall', [datetime(2026,3,29,1,30),datetime(2026,10,25,1,30)])
def test_dst_gap_and_fold_are_rejected(wall):
    with pytest.raises(ValueError, match='Ambiguous or nonexistent'):
        resolve_instant(wall,'Europe/London')


def test_unknown_hour_on_term_boundary_rejected():
    patron=Patron(patron_id='REF',birth_date=date(2024,2,4),gender='male',birth_timezone='Asia/Shanghai')
    with pytest.raises(ValueError, match='solar-term boundary'):
        calculate_context(patron,date(2026,11,20))
