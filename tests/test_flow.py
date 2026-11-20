import asyncio
from datetime import date
from unittest.mock import AsyncMock, Mock
import pytest
from fastapi.testclient import TestClient
from app.config import Settings, ApiSettings
from app.main import app, authorize, repository
from app.models import CatalogEntry, Patron
from app.service import FortuneService


@pytest.fixture(autouse=True)
def api_lifespan_dependencies(monkeypatch):
    # These workflow tests override the repository, so no real database is needed.
    monkeypatch.setattr('app.main.get_api_settings', lambda: ApiSettings(
        _env_file=None, database_dsn='unused', api_key='test'))
    monkeypatch.setattr('app.main.DatabasePool', Mock())


class MemoryRepository:
    def __init__(self):
        self.saved = None
        self.writes = 0
        self.audit = None

    def get_fortune(self, patron_id, target_date):
        return self.saved

    def catalog(self, kind):
        return [CatalogEntry(id=kind, name=kind,
                             metadata={'elements': ['wood', 'fire', 'earth', 'metal', 'water']})]

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


def test_missing_element_catalog_never_publishes_partial_fortune():
    repo = MemoryRepository()
    repo.catalog = lambda kind: [CatalogEntry(id=kind, name=kind, metadata={'elements': ['metal']})]
    generator = service(repo)
    generator.llm.generate = AsyncMock()
    with pytest.raises(ExceptionGroup):
        asyncio.run(generator.generate(Patron(patron_id='P001'), date(2026,11,20)))
    assert repo.writes == 0
    generator.llm.generate.assert_not_awaited()


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
    assert result.rules_version == 'daily-theme-v8'
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


def test_support_decision_drives_recommendations_qwen_and_persisted_audit():
    repo = MemoryRepository()
    generator = service(repo)
    generator.taibu.context = AsyncMock(return_value={
        'personalization': 'four_pillars',
        'coordinates': {'day_stem': '戊', 'day_branch': '戌',
                        'day_master': '丙', 'natal': []},
    })
    original = generator.llm.generate
    generator.llm.generate = AsyncMock(side_effect=original)
    result = asyncio.run(generator.generate(Patron(patron_id='P001'), date(2026,11,20)))
    assert result.rules_version == 'daily-theme-v8'
    assert result.lucky_number == 3
    assert result.lucky_color.name == 'Green'
    decision = repo.audit['element_decision']
    assert decision['day_master_element'] == 'fire'
    assert decision['day_element'] == 'earth'
    assert decision['relationship'] == 'generated_by_master'
    assert decision['element'] == repo.audit['reading']['element'] == 'wood'
    assert decision['strategy'] == 'support'
    assert decision['reason']
    assert 'theme_candidates' not in repo.audit
    for kind in ('item', 'dining'):
        catalog_decision = repo.audit['catalog_decisions'][kind]
        assert catalog_decision['required_element'] == 'wood'
        assert catalog_decision['candidate_ids'] == [kind]
        assert catalog_decision['matched_tags'] == {'elements': ['wood'], 'zodiacs': [], 'colors': []}
    for call in generator.llm.generate.await_args_list:
        assert call.args[1]['element_decision'] == decision
        assert call.args[1]['daily_reading'] == {'element': 'wood'}
        assert call.args[1]['lucky_zodiac'] == result.lucky_zodiac.value


def test_personal_zodiac_and_trace_reach_qwen_and_persisted_audit():
    repo = MemoryRepository()
    generator = service(repo)
    generator.taibu.context = AsyncMock(return_value={
        'personalization': 'four_pillars',
        'coordinates': {'day_stem': '甲', 'day_branch': '子', 'day_master': '丙',
                        'natal': [{'label': label, 'branch': branch} for label, branch in
                                  zip(('year', 'month', 'day', 'hour'), '卯午酉巳')]},
    })
    original = generator.llm.generate
    generator.llm.generate = AsyncMock(side_effect=original)
    result = asyncio.run(generator.generate(Patron(patron_id='P001'), date(2026,11,20)))
    assert result.lucky_zodiac.value == 'Dragon'
    decision = repo.audit['zodiac_decision']
    assert decision['base_candidates'] == ['辰', '未', '申', '戌']
    assert decision['preferred_candidates'] == ['辰', '申']
    assert decision['selected_branch'] == '辰'
    assert decision['zodiac'] == result.lucky_zodiac.value
    assert decision['daily_relationship'] == 'trine_group'
    assert decision['reason']
    for call in generator.llm.generate.await_args_list:
        assert call.args[1]['zodiac_decision'] == decision


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
