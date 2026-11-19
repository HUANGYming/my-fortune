import asyncio
from unittest.mock import AsyncMock
import pytest
from app.models import CatalogEntry
from app.recommendations import lucky_item, lucky_dining
from app.seed import seed_sql
import sqlite3
from pathlib import Path


def context():
    return {'date': '2026-11-19', 'profile': {},
            'daily_reading': {'element': 'metal', 'theme': 'Quiet elegance'},
            'lucky_color': {'name': 'Gold'}}


def test_item_llm_can_select_lower_scored_candidate_and_records_reason():
    data = context()
    entries = [CatalogEntry(id='high', name='Gold Earrings', metadata={'elements': ['metal']}),
               CatalogEntry(id='low', name='Silk Scarf')]
    llm = AsyncMock()
    llm.generate.return_value = lucky_item.Selection(entry_id='low', reason='Fits a softer style')
    result = asyncio.run(lucky_item.generate(llm, data, entries))
    assert result.id == 'low'
    assert data['catalog_decisions']['item']['reason'] == 'Fits a softer style'
    assert len(llm.generate.call_args.args[1]['candidates']) == 2


def test_dining_model_cannot_select_unknown_candidate():
    data = context()
    entries = [CatalogEntry(id='unsafe', name='Peanut Kitchen', metadata={'allergens': ['peanut']}),
               CatalogEntry(id='safe', name='Garden', metadata={'allergens': []})]
    llm = AsyncMock()
    llm.generate.return_value = lucky_dining.Selection(entry_id='unknown', reason='Incorrect choice')
    with pytest.raises(ValueError, match='outside the eligible candidates'):
        asyncio.run(lucky_dining.generate(llm, data, entries))
    assert [entry['id'] for entry in llm.generate.call_args.args[1]['candidates']] == ['safe', 'unsafe']
    assert 'catalog_decisions' not in data


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
        assert connection.execute('SELECT COUNT(*) FROM fortune_catalog').fetchone()[0] == 12
    finally:
        connection.close()
