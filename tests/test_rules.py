import pytest
from datetime import date
from app.models import CatalogEntry
from app.rules import select_catalog, daily_element_decision
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


@pytest.mark.parametrize(('master', 'expected'), [
    ('甲', ('wood', 'water', 'wood', 'water', 'water')),
    ('丙', ('wood', 'fire', 'wood', 'fire', 'wood')),
    ('戊', ('fire', 'fire', 'earth', 'fire', 'earth')),
    ('庚', ('metal', 'earth', 'earth', 'metal', 'earth')),
    ('壬', ('metal', 'water', 'metal', 'metal', 'water')),
])
def test_support_policy_for_every_personal_and_daily_element(master, expected):
    # Each row exercises all five daily elements, including 泄、耗、克.
    for stem, element in zip('甲丙戊庚壬', expected):
        decision = daily_element_decision({'coordinates': {
            'day_stem': stem, 'day_master': master,
        }})
        assert decision['strategy'] == 'support'
        assert decision['element'] == element
        assert decision['reason']


@pytest.mark.parametrize(('stem', 'relationship'), [
    ('甲', 'generates_master'), ('丙', 'same'),
    ('戊', 'generated_by_master'), ('庚', 'controlled_by_master'),
    ('壬', 'controls_master'),
])
def test_support_decision_records_the_relationship_for_audit(stem, relationship):
    decision = daily_element_decision({'coordinates': {
        'day_stem': stem, 'day_master': '丙',
    }})
    assert decision['day_master_element'] == 'fire'
    assert decision['relationship'] == relationship
    # Yin/Yang stems of the same element follow the same editorial policy.
    assert daily_element_decision({'coordinates': {
        'day_stem': stem, 'day_master': '丁',
    }}) == decision


def test_fields_share_element_and_avoid_daily_clash():
    data = context()
    assert lucky_number.generate(data) in (4, 9)
    assert lucky_color.generate(data).name in ('Gold', 'Silver')
    assert lucky_zodiac.generate(data).value != 'Monkey'
    assert lucky_zodiac.generate(data) == lucky_zodiac.generate(data)


def test_catalog_ranking_uses_theme_and_color():
    from app.rules import rank_catalog
    entries = [CatalogEntry(id='a', name='Generic'),
               CatalogEntry(id='b', name='Theme', metadata={'elements': ['metal']}),
               CatalogEntry(id='c', name='Both', metadata={'elements': ['metal'], 'colors': ['gold']})]
    assert [entry.id for entry in rank_catalog(context(), entries, 'item')] == ['c', 'b']
    with pytest.raises(ValueError):
        rank_catalog(context(), [], 'dining')


def test_color_uses_theme_and_date_independently_of_legacy_preferences():
    data = context()
    expected = lucky_color.generate(data)
    data['profile']['preferences'] = {'preferred_colors': [
        'Silver' if expected.name == 'Gold' else 'Gold'
    ]}
    assert lucky_color.generate(data) == expected
    del data['profile']
    assert lucky_color.generate(data) == expected


@pytest.mark.parametrize('coordinates', [
    {'day_stem': '戊'}, {'day_stem': '戊', 'day_master': None},
])
def test_missing_day_master_uses_daily_element_without_personal_support(coordinates):
    decision = daily_element_decision({'coordinates': coordinates})
    assert decision['strategy'] == 'general'
    assert decision['day_master_element'] is None
    assert decision['day_element'] == decision['element'] == 'earth'
    assert decision['relationship'] is None
    assert decision['reason']


def test_color_palette_uses_exactly_the_ten_product_colors():
    from datetime import timedelta
    from app.recommendations.lucky_color import PALETTES
    expected = {'Red','Blue','Purple','Green','Yellow','Gold','Silver','Orange','Brown','Pink'}
    assert {name for palette in PALETTES.values() for name, _ in palette} == expected
    assert sum(len(palette) for palette in PALETTES.values()) == 10
    seen = set()
    for element, palette in PALETTES.items():
        for offset in range(len(palette)):
            data = context()
            data['daily_reading']['element'] = element
            data['date'] = (date(2026,11,20) + timedelta(days=offset)).isoformat()
            color = lucky_color.generate(data)
            seen.add(color.name)
            assert color == lucky_color.generate(data)
    assert seen == expected
