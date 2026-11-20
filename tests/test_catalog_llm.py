import asyncio
from unittest.mock import AsyncMock
import pytest
from app.models import CatalogEntry
from app.recommendations import lucky_item, lucky_dining
from app.rules import rank_catalog
from app.seed import seed_sql
import sqlite3
from pathlib import Path


def context():
    return {'date': '2026-11-19', 'profile': {},
            'daily_reading': {'element': 'metal'},
            'lucky_color': {'name': 'Gold'}, 'lucky_zodiac': 'Tiger'}


def test_item_llm_can_select_lower_priority_eligible_candidate_and_records_matches():
    data = context()
    entries = [CatalogEntry(id='high', name='Gold Earrings', metadata={
                   'elements': ['metal'], 'zodiacs': ['Tiger'], 'colors': ['gold']}),
               CatalogEntry(id='low', name='Silver Bracelet', metadata={'elements': ['metal']})]
    llm = AsyncMock()
    llm.generate.return_value = lucky_item.Selection(entry_id='low', reason='An eligible metal accessory')
    result = asyncio.run(lucky_item.generate(llm, data, entries))
    assert result.id == 'low'
    assert data['catalog_decisions']['item']['reason'] == 'An eligible metal accessory'
    assert data['catalog_decisions']['item']['matched_tags'] == {
        'elements': ['metal'], 'zodiacs': [], 'colors': []}
    assert len(llm.generate.call_args.args[1]['candidates']) == 2


def test_dining_model_cannot_select_unknown_candidate():
    data = context()
    entries = [CatalogEntry(id='b', name='Silver Room', metadata={'elements': ['metal']}),
               CatalogEntry(id='a', name='Golden Room', metadata={'elements': ['metal']})]
    llm = AsyncMock()
    llm.generate.return_value = lucky_dining.Selection(entry_id='unknown', reason='Incorrect choice')
    with pytest.raises(ValueError, match='outside the eligible candidates'):
        asyncio.run(lucky_dining.generate(llm, data, entries))
    assert [entry['id'] for entry in llm.generate.call_args.args[1]['candidates']] == ['a', 'b']
    assert 'catalog_decisions' not in data


@pytest.mark.parametrize('module', [lucky_item, lucky_dining])
def test_element_is_required_even_when_zodiac_and_color_match(module):
    data = context()
    entries = [
        CatalogEntry(id='allowed', name='Metal entry', metadata={
            'elements': ['earth', 'metal'], 'zodiacs': ['Tiger', 'Horse'], 'colors': ['gold']}),
        CatalogEntry(id='excluded', name='Wrong element', metadata={
            'elements': ['wood'], 'zodiacs': ['Tiger'], 'colors': ['gold']}),
        CatalogEntry(id='untagged', name='No element'),
    ]
    llm = AsyncMock()
    llm.generate.return_value = module.Selection(entry_id='allowed', reason='Matches supplied tags')
    assert asyncio.run(module.generate(llm, data, entries)).id == 'allowed'
    candidates = llm.generate.call_args.args[1]['candidates']
    assert [entry['id'] for entry in candidates] == ['allowed']
    assert candidates[0]['rule_matches'] == {'element': True, 'zodiac': True, 'color': True}
    kind = 'item' if module is lucky_item else 'dining'
    assert data['catalog_decisions'][kind]['matched_tags'] == {
        'elements': ['metal'], 'zodiacs': ['Tiger'], 'colors': ['Gold']}


@pytest.mark.parametrize('module', [lucky_item, lucky_dining])
def test_model_cannot_select_an_existing_but_filtered_out_entry(module):
    data = context()
    entries = [CatalogEntry(id='allowed', name='Metal', metadata={'elements': ['metal']}),
               CatalogEntry(id='excluded', name='Wood', metadata={'elements': ['wood']})]
    llm = AsyncMock()
    llm.generate.return_value = module.Selection(entry_id='excluded', reason='Wrong element')
    with pytest.raises(ValueError, match='outside the eligible candidates'):
        asyncio.run(module.generate(llm, data, entries))
    assert 'catalog_decisions' not in data


@pytest.mark.parametrize('module', [lucky_item, lucky_dining])
def test_missing_matching_element_fails_before_calling_qwen(module):
    llm = AsyncMock()
    with pytest.raises(ValueError, match='No eligible .* candidate for element metal'):
        asyncio.run(module.generate(llm, context(), [
            CatalogEntry(id='wrong', name='Wood', metadata={'elements': ['wood']}),
        ]))
    llm.generate.assert_not_awaited()


def test_zodiac_priority_precedes_color_without_excluding_untagged_entries():
    entries = [
        CatalogEntry(id='a', name='Color', metadata={'elements': ['metal'], 'colors': ['gold']}),
        CatalogEntry(id='b', name='Zodiac', metadata={'elements': ['metal'], 'zodiacs': ['Tiger']}),
        CatalogEntry(id='c', name='Both', metadata={
            'elements': ['metal'], 'zodiacs': ['Tiger'], 'colors': ['GOLD']}),
        CatalogEntry(id='d', name='Optional tags absent', metadata={'elements': ['metal']}),
        CatalogEntry(id='e', name='Other zodiac', metadata={'elements': ['metal'], 'zodiacs': ['Rabbit']}),
    ]
    assert [entry.id for entry in rank_catalog(context(), entries, 'item')] == ['c', 'b', 'a', 'd', 'e']
    data = context()
    data['lucky_zodiac'] = 'Pig'
    assert [entry.id for entry in rank_catalog(data, entries, 'item')] == ['a', 'c', 'b', 'd', 'e']


@pytest.mark.parametrize(('field', 'value'), [
    ('elements', 'metal'), ('elements', ['unknown']),
    ('zodiacs', 'Tiger'), ('zodiacs', ['tiger']), ('colors', [123]),
])
def test_malformed_catalog_tags_are_reported_instead_of_matching_as_substrings(field, value):
    entry = CatalogEntry(id='bad', name='Bad tags', metadata={'elements': ['metal'], field: value})
    with pytest.raises(ValueError, match=f'Invalid {field} tags for catalog entry bad'):
        rank_catalog(context(), [entry], 'item')


@pytest.mark.parametrize('module', [lucky_item, lucky_dining])
def test_zodiac_priority_is_applied_before_twenty_candidate_limit(module):
    entries = [CatalogEntry(id=f'a{i:02}', name='Metal', metadata={'elements': ['metal']})
               for i in range(25)]
    entries.append(CatalogEntry(id='z', name='Tiger metal', metadata={
        'elements': ['metal'], 'zodiacs': ['Tiger']}))
    data = context()
    llm = AsyncMock()
    llm.generate.return_value = module.Selection(entry_id='z', reason='Matches metal and Tiger')
    asyncio.run(module.generate(llm, data, entries))
    candidates = llm.generate.call_args.args[1]['candidates']
    assert len(candidates) == 20
    assert candidates[0]['id'] == 'z'
    assert 'a24' not in [entry['id'] for entry in candidates]


def test_llm_seed_inputs_preserve_published_results():
    root = Path(__file__).resolve().parents[1]
    connection = sqlite3.connect(':memory:')
    try:
        connection.executescript((root / 'sql/001_schema.sql').read_text())
        connection.executescript(seed_sql(False))
        before = connection.execute('SELECT payload FROM my_fortunes ORDER BY patron_id, fortune_date').fetchall()
        connection.executescript(seed_sql(True))
        after = connection.execute('SELECT payload FROM my_fortunes ORDER BY patron_id, fortune_date').fetchall()
        assert before == after
        assert connection.execute('SELECT COUNT(*) FROM fortune_catalog').fetchone()[0] == 20
    finally:
        connection.close()
