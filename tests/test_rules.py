import pytest
from app.models import CatalogEntry
from app.rules import select_catalog, theme_candidates
from app.recommendations import lucky_color, lucky_number, lucky_zodiac


def context():
    return {
        'date': '2026-11-20',
        'profile': {'preferences': {}},
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


def test_dining_restrictions_precede_element_score():
    data = context()
    data['profile']['preferences'] = {'allergens': ['peanut'], 'dietary_requirements': ['vegetarian']}
    catalog = [
        CatalogEntry(id='unsafe', name='Unsafe', metadata={'elements': ['metal'], 'allergens': ['peanut']}),
        CatalogEntry(id='unknown', name='Unknown'),
        CatalogEntry(id='safe', name='Safe', metadata={'allergens': [], 'dietary_options': ['vegetarian']}),
    ]
    assert select_catalog(data, catalog, 'dining').id == 'safe'
    with pytest.raises(ValueError):
        select_catalog(data, catalog[:2], 'dining')


def test_item_material_exclusion_precedes_theme_score():
    data = context()
    data['profile']['preferences'] = {'excluded_materials': ['nickel']}
    entries = [CatalogEntry(id='bad', name='Earrings', metadata={'elements': ['metal'], 'materials': ['nickel']}),
               CatalogEntry(id='good', name='Scarf')]
    assert select_catalog(data, entries, 'item').id == 'good'
