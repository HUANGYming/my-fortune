import asyncio
from datetime import date
from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import app, authorize, repository
from app.models import CatalogEntry, Patron
from app.service import FortuneService


class MemoryRepository:
    def __init__(self):
        self.saved = None
        self.writes = 0
        self.audit = None

    def get_fortune(self, patron_id, target_date):
        return self.saved

    def catalog(self, kind):
        return [CatalogEntry(id=kind, name=kind)]

    def save(self, fortune, audit):
        self.saved = fortune
        self.audit = audit
        self.writes += 1


class FakeLLM:
    async def generate(self, task, context, schema):
        if 'entry_id' in schema.model_fields:
            return schema(entry_id=context['candidates'][0]['id'], reason='Matches supplied daily theme')
        raise AssertionError('Only item and dining may call the model')


def service(repo):
    settings = Settings(database_dsn='unused', api_key='test', qwen_base_url='http://qwen/v1',
                        qwen_model='Qwen')
    instance = FortuneService(settings, repo)
    instance.llm = FakeLLM()
    instance.taibu.context = AsyncMock(return_value={'almanac': {'day': 'example'}, 'personalization': 'general',
        'coordinates': {'day_stem': '甲', 'day_branch': '寅', 'day_master': None, 'natal': []}})
    return instance


def test_generation_persists_all_five_and_rerun_skips_model():
    repo = MemoryRepository()
    generator = service(repo)
    patron = Patron(patron_id='P001')
    target = date(2026, 11, 20)
    result = asyncio.run(generator.generate(patron, target))
    assert result.lucky_number in (3, 8)
    assert result.lucky_zodiac.value != 'Monkey'
    assert result.lucky_color.name in ('Green',)
    assert result.lucky_item.id == 'item'
    assert result.lucky_dining.id == 'dining'
    generator.llm.generate = AsyncMock(side_effect=AssertionError('Must read persisted result'))
    assert asyncio.run(generator.generate(patron, target)) == result
    assert repo.writes == 1


def test_invalid_final_selection_never_publishes_partial_fortune():
    repo = MemoryRepository()
    generator = service(repo)
    original = generator.llm.generate

    async def select_invalid_dining(task, context, schema):
        if "Choose one dining" in task:
            return schema(entry_id="unknown", reason="Invalid test selection")
        return await original(task, context, schema)

    generator.llm.generate = select_invalid_dining
    with pytest.raises(ExceptionGroup):
        asyncio.run(generator.generate(Patron(patron_id='P001'), date(2026, 11, 20)))
    assert repo.writes == 0


def test_query_returns_missing_without_generation_and_validates_dates():
    app.dependency_overrides[authorize] = lambda: None
    app.dependency_overrides[repository] = MemoryRepository
    try:
        with TestClient(app) as client:
            assert client.get('/v1/patrons/P001/fortunes/2026-11-20').status_code == 404
            assert client.get('/v1/patrons/P001/fortunes/bad-date').status_code == 422
            assert '/v1/patrons/{patron_id}/fortunes/today' in client.get('/openapi.json').json()['paths']
    finally:
        app.dependency_overrides.clear()


def test_actual_taibu_through_generation_to_persisted_query():
    from app.taibu import TaibuClient

    repo = MemoryRepository()
    generator = service(repo)
    generator.taibu = TaibuClient(generator.settings)
    patron = Patron(patron_id='P001', birth_date=date(1990, 1, 15), birth_hour=9,
                    birth_timezone='Asia/Shanghai', gender='male')
    result = asyncio.run(generator.generate(patron, date(2026, 11, 20)))
    assert result.personalization == 'four_pillars'
    assert result.rules_version == 'daily-theme-v5'
    assert result.lucky_number in (5, 0)
    assert repo.writes == 1
    app.dependency_overrides[authorize] = lambda: None
    app.dependency_overrides[repository] = lambda: repo
    try:
        with TestClient(app) as client:
            response = client.get('/v1/patrons/P001/fortunes/2026-11-20')
            assert response.status_code == 200
            assert response.json() == result.model_dump(mode='json')
    finally:
        app.dependency_overrides.clear()


def test_only_item_and_dining_call_qwen():
    repo = MemoryRepository()
    generator = service(repo)
    original = generator.llm.generate
    generator.llm.generate = AsyncMock(side_effect=original)
    asyncio.run(generator.generate(Patron(patron_id='P001'), date(2026,11,20)))
    calls = generator.llm.generate.await_args_list
    assert len(calls) == 2
    assert 'Choose one item' in calls[0].args[0]
    assert 'Choose one dining' in calls[1].args[0]
    assert calls[0].args[1]['daily_reading'] == {'element':'wood'}
    assert repo.audit['reading'] == {'element':'wood'}


def test_item_and_dining_run_independently_and_concurrently():
    async def exercise():
        repo = MemoryRepository()
        generator = service(repo)
        started = set()
        both_started = asyncio.Event()
        original = generator.llm.generate

        async def generate(task, context, schema):
            assert 'selected_item' not in context
            started.add('item' if 'Choose one item' in task else 'dining')
            if len(started) == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=5)
            return await original(task, context, schema)

        generator.llm.generate = generate
        await generator.generate(Patron(patron_id='P001'), date(2026,11,20))
        assert set(repo.audit['catalog_decisions']) == {'item','dining'}
        assert repo.writes == 1

    asyncio.run(exercise())
