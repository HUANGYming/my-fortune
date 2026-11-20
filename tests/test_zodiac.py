from copy import deepcopy
from datetime import date, timedelta

import pytest

from app.recommendations import lucky_zodiac


def context(natal=(), daily='子', target_date=date(2026, 11, 20)):
    return {'date': target_date.isoformat(), 'facts': {'coordinates': {
        'day_branch': daily,
        'natal': [{'label': label, 'branch': branch}
                  for label, branch in zip(('year', 'month', 'day', 'hour'), natal)],
    }}}


@pytest.mark.parametrize(('branch', 'expected'), [
    ('子', 'Ox'), ('丑', 'Rat'), ('寅', 'Pig'), ('卯', 'Dog'),
    ('辰', 'Rooster'), ('巳', 'Monkey'), ('午', 'Goat'), ('未', 'Horse'),
    ('申', 'Snake'), ('酉', 'Dragon'), ('戌', 'Rabbit'), ('亥', 'Tiger'),
])
def test_personal_combine_for_each_branch(branch, expected):
    # A sole personal candidate wins even without a relation to today's branch.
    data = context((branch,), daily=branch)
    assert lucky_zodiac.generate(data).value == expected
    assert data['zodiac_decision']['candidate_source'] == 'personal_combines'


def test_month_and_hour_join_year_and_day_without_pillar_weights():
    data = context(('子', '午', '酉', '戌'))
    lucky_zodiac.generate(data)
    decision = data['zodiac_decision']
    assert decision['base_candidates'] == ['丑', '卯', '辰', '未']
    assert decision['candidate_origins'] == [
        {'label': 'year', 'branch': '子', 'candidate': '丑'},
        {'label': 'month', 'branch': '午', 'candidate': '未'},
        {'label': 'day', 'branch': '酉', 'candidate': '辰'},
        {'label': 'hour', 'branch': '戌', 'candidate': '卯'},
    ]


def test_duplicate_branches_do_not_add_weight_and_order_is_stable():
    data = context(('子', '午'), daily='戌')
    expected = lucky_zodiac.generate(data)
    repeated = context(('午', '子', '午', '子'), daily='戌')
    assert lucky_zodiac.generate(repeated) == expected
    assert repeated['zodiac_decision']['base_candidates'] == ['丑', '未']
    assert repeated['zodiac_decision']['selection_pool'] == ['丑', '未']


def test_only_daily_clash_excludes_a_personal_candidate():
    data = context(('子', '午'), daily='未')
    assert lucky_zodiac.generate(data).value == 'Goat'
    assert data['zodiac_decision']['base_excluded'] == ['丑']
    assert data['zodiac_decision']['eligible_candidates'] == ['未']


def test_other_natal_pillars_do_not_veto_personal_combines():
    # 丑冲未、午冲子, but only clashes with today's 申 are a hard exclusion.
    data = context(('子', '未'), daily='申')
    lucky_zodiac.generate(data)
    assert data['zodiac_decision']['eligible_candidates'] == ['丑', '午']
    assert data['zodiac_decision']['base_excluded'] == []


def test_daily_combine_and_trine_partners_share_priority_and_rotate():
    seen = set()
    for offset in range(3):
        data = context(('子', '酉', '巳'), target_date=date(2026,11,20) + timedelta(days=offset))
        result = lucky_zodiac.generate(data)
        # 子丑六合 and 申子辰三合-group partners all remain in one priority tier.
        assert data['zodiac_decision']['preferred_candidates'] == ['丑', '辰', '申']
        assert data['zodiac_decision']['selection_pool'] == ['丑', '辰', '申']
        assert lucky_zodiac.generate(deepcopy(data)) == result
        seen.add(result.value)
    assert seen == {'Ox', 'Dragon', 'Monkey'}


def test_no_daily_affinity_rotates_remaining_candidates():
    seen = set()
    for offset in range(2):
        data = context(('子', '午'), daily='戌', target_date=date(2026,11,20) + timedelta(days=offset))
        seen.add(lucky_zodiac.generate(data).value)
        assert data['zodiac_decision']['preferred_candidates'] == []
        assert data['zodiac_decision']['selection_pool'] == ['丑', '未']
        assert data['zodiac_decision']['daily_relationship'] == 'neutral'
    assert seen == {'Ox', 'Goat'}


def test_all_personal_combines_clash_then_expand_personal_trine_partners():
    data = context(('巳', '巳', '巳'), daily='寅')
    assert lucky_zodiac.generate(data).value == 'Ox'
    decision = data['zodiac_decision']
    assert decision['base_candidates'] == decision['base_excluded'] == ['申']
    assert decision['candidate_source'] == 'personal_trines'
    assert decision['fallback_candidates'] == ['丑', '酉']
    assert decision['eligible_candidates'] == ['丑', '酉']
    assert decision['selected_branch'] != '申'
    assert decision['reason']


def test_missing_hour_uses_only_the_three_known_pillars():
    data = context(('子', '午', '酉'))
    lucky_zodiac.generate(data)
    assert data['zodiac_decision']['base_candidates'] == ['丑', '辰', '未']
    assert [entry['label'] for entry in data['zodiac_decision']['personal_branches']] == ['year', 'month', 'day']


@pytest.mark.parametrize('natal_present', [False, True])
def test_no_personal_pillars_falls_back_to_daily_combine(natal_present):
    data = context(daily='寅')
    if not natal_present:
        del data['facts']['coordinates']['natal']
    assert lucky_zodiac.generate(data).value == 'Pig'
    assert data['zodiac_decision']['candidate_source'] == 'daily_combine'
    assert data['zodiac_decision']['personal_branches'] == []


def test_same_day_can_produce_different_personal_zodiacs():
    assert lucky_zodiac.generate(context(('子',))).value == 'Ox'
    assert lucky_zodiac.generate(context(('卯',))).value == 'Dog'


@pytest.mark.parametrize(('daily', 'clash'), [
    ('子', '午'), ('丑', '未'), ('寅', '申'), ('卯', '酉'),
    ('辰', '戌'), ('巳', '亥'), ('午', '子'), ('未', '丑'),
    ('申', '寅'), ('酉', '卯'), ('戌', '辰'), ('亥', '巳'),
])
def test_every_personal_branch_has_a_result_without_daily_clash(daily, clash):
    for personal in '子丑寅卯辰巳午未申酉戌亥':
        data = context((personal,), daily=daily)
        lucky_zodiac.generate(data)
        decision = data['zodiac_decision']
        assert decision['selected_branch'] != clash
        assert decision['selected_branch'] in decision['selection_pool']
