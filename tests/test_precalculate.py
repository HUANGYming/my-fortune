import asyncio
from contextlib import contextmanager
from datetime import date
import sqlite3
from unittest.mock import AsyncMock
from app import precalculate
from app.config import Settings
from app.models import Patron
from app.repository import Repository


def test_full_table_batch_continues_after_patron_failure(monkeypatch):
    class FakeRepository:
        def iter_patron_ids(self, batch_size):
            assert batch_size == 2
            yield from ('P001', 'P002', 'P003')

        def get_patron(self, patron_id):
            if patron_id == 'P002':
                raise ValueError('Invalid birth record')
            return Patron(patron_id=patron_id)

    service = AsyncMock()
    monkeypatch.setattr(precalculate, 'get_settings', lambda: object())
    monkeypatch.setattr(precalculate, 'Repository', lambda settings: FakeRepository())
    monkeypatch.setattr(precalculate, 'FortuneService', lambda settings, repo: service)
    failures = asyncio.run(precalculate.run(date(2026,11,20), batch_size=2))
    assert failures == 1
    assert sorted(call.args[0].patron_id for call in service.generate.await_args_list) == ['P001','P003']


def test_patron_pagination_reads_every_distinct_id(monkeypatch):
    db = sqlite3.connect(':memory:')
    db.execute('CREATE TABLE fortune_patron_source (patron_id TEXT)')
    expected = [f'P{i:04}' for i in range(1201)]
    db.executemany('INSERT INTO fortune_patron_source VALUES (?)', [(value,) for value in expected + ['P0000']])

    class Cursor:
        def __enter__(self):
            self.cursor = db.cursor()
            return self

        def __exit__(self, *args):
            self.cursor.close()

        def execute(self, query, values):
            self.cursor.execute(query.replace('%s','?'), values)

        def fetchall(self):
            return self.cursor.fetchall()

    class Connection:
        def cursor(self):
            return Cursor()

    @contextmanager
    def connection(settings):
        yield Connection()

    monkeypatch.setattr('app.repository.connection', connection)
    settings = Settings(database_dsn='unused',api_key='test',qwen_base_url='http://unused',qwen_model='Qwen')
    try:
        assert list(Repository(settings).iter_patron_ids(500)) == expected
    finally:
        db.close()


def test_full_table_concurrency_is_bounded_and_every_patron_is_processed(monkeypatch):
    async def exercise():
        active = 0
        peak = 0
        seen = set()
        gate = asyncio.Event()
        ids = [f'P{i:03}' for i in range(70)]

        class FakeRepository:
            def iter_patron_ids(self, batch_size):
                yield from ids

            def get_patron(self, patron_id):
                return Patron(patron_id=patron_id)

        async def generate(patron, target_date):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            seen.add(patron.patron_id)
            if active == 16:
                gate.set()
            try:
                await asyncio.wait_for(gate.wait(), timeout=5)
                await asyncio.sleep(0)
                if patron.patron_id == 'P020':
                    raise ValueError('Recoverable individual failure')
            finally:
                active -= 1

        service = AsyncMock()
        service.generate.side_effect = generate
        monkeypatch.setattr(precalculate, 'get_settings', lambda: object())
        monkeypatch.setattr(precalculate, 'Repository', lambda settings: FakeRepository())
        monkeypatch.setattr(precalculate, 'FortuneService', lambda settings, repo: service)
        failures = await precalculate.run(date(2026,11,20))
        assert failures == 1
        assert peak == 16
        assert active == 0
        assert seen == set(ids)

    asyncio.run(exercise())
