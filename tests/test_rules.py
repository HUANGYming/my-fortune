import pytest
from app.models import CatalogEntry
from app.rules import select_catalog, theme_candidates, select_daily_element
from datetime import date
from app.recommendations import lucky_color, lucky_number, lucky_zodiac


def context():
    return {
        'date': '2026-11-20',
        'profile': {},
        'daily_reading': {'element': 'metal'},
        'lucky_color': {'name': 'Gold'},
        'facts': {'coordinates': {'day_stem': '甲', 'day_branch': '寅',
                                 'day_master': '丁', 'natal': []}},
    }


def test_theme_candidates_use_daily_and_personal_stems():
    candidates = theme_candidates(context()['facts'])
    assert {candidate['element'] for candidate in candidates} == {'wood', 'fire'}


def test_fields_share_element_and_avoid_daily_clash():
    data = context()
    assert lucky_number.generate(data) in (4, 9)
    assert lucky_color.generate(data).name in ('Gold', 'White')
    assert lucky_zodiac.generate(data).value != 'Monkey'
    assert lucky_zodiac.generate(data) == lucky_zodiac.generate(data)


def test_catalog_ranking_uses_theme_and_color():
    from app.rules import rank_catalog
    entries = [CatalogEntry(id='a', name='Generic'),
               CatalogEntry(id='b', name='Theme', metadata={'elements': ['metal']}),
               CatalogEntry(id='c', name='Both', metadata={'elements': ['metal'], 'colors': ['gold']})]
    assert [(score, entry.id) for score, entry in rank_catalog(context(), entries, 'item')] == [
        (7, 'c'), (5, 'b'), (0, 'a')]
    with pytest.raises(ValueError):
        rank_catalog(context(), [], 'dining')


def test_color_uses_theme_and_date_independently_of_legacy_preferences():
    data = context()
    expected = lucky_color.generate(data)
    data['profile']['preferences'] = {'preferred_colors': [
        'White' if expected.name == 'Gold' else 'Gold'
    ]}
    assert lucky_color.generate(data) == expected
    del data['profile']
    assert lucky_color.generate(data) == expected


def test_rule_element_uses_highest_score_and_rotates_ties():
    facts = {'coordinates': {'day_stem':'戊', 'day_master':'庚'}}
    candidates = theme_candidates(facts)
    assert select_daily_element(candidates,date(2026,11,20)) == 'earth'
    tied = theme_candidates({'coordinates':{'day_stem':'戊','day_master':'丁'}})
    first = select_daily_element(tied,date(2026,11,20))
    second = select_daily_element(tied,date(2026,11,21))
    assert {first,second} == {'fire','earth'}
    assert select_daily_element(tied,date(2026,11,20)) == first
    with pytest.raises(ValueError):
        select_daily_element([],date(2026,11,20))
