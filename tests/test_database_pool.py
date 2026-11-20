from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
from threading import Event
from unittest.mock import Mock

import psycopg2
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import ApiSettings, get_api_settings
from app.database import DatabasePool, PoolBusyError, connection
from app.main import app


def settings(**overrides):
    return ApiSettings(_env_file=None, database_dsn='unused', api_key='test',
                       **overrides)


class FakeConnection:
    def __init__(self, health_error=None):
        self.closed = False
        self.health_error = health_error
        self.queries = []
        self.commits = 0
        self.rollbacks = 0
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc_type:
            self.rollbacks += 1
        else:
            self.commits += 1

    @contextmanager
    def cursor(self):
        yield self

    def execute(self, sql, parameters=None):
        self.queries.append((sql, parameters))
        if sql == 'SELECT 1' and self.health_error:
            raise self.health_error

    def fetchone(self):
        return self.result

    def close(self):
        self.closed = True


def make_pool(monkeypatch, **overrides):
    driver = Mock()
    conn = FakeConnection()
    driver.getconn.return_value = conn
    factory = Mock(return_value=driver)
    monkeypatch.setattr('app.database.ThreadedConnectionPool', factory)
    pool = DatabasePool(settings(**overrides))
    return pool, driver, conn


def test_connections_are_reused_and_transactions_finish(monkeypatch):
    pool, driver, conn = make_pool(monkeypatch)
    for _ in range(2):
        with pool.connection() as borrowed:
            assert borrowed is conn
    assert conn.commits == 4  # Health check and request transaction per checkout.
    assert not conn.closed
    assert driver.putconn.call_count == 2
    driver.putconn.assert_called_with(conn, close=False)
    pool.close()
    pool.close()
    driver.closeall.assert_called_once()
    with pytest.raises(RuntimeError, match='closed'):
        with pool.connection():
            pass


def test_caller_error_rolls_back_and_releases_slot(monkeypatch):
    pool, driver, conn = make_pool(monkeypatch, api_db_pool_min=1, api_db_pool_max=1)
    with pytest.raises(ValueError):
        with pool.connection():
            raise ValueError('Caller failure')
    assert conn.rollbacks == 1
    driver.putconn.assert_called_with(conn, close=False)
    with pool.connection():
        pass


def test_stale_connection_is_discarded_before_request(monkeypatch):
    pool, driver, _ = make_pool(monkeypatch)
    stale = FakeConnection(psycopg2.OperationalError('Idle connection lost'))
    healthy = FakeConnection()
    driver.getconn.side_effect = [stale, healthy]
    with pool.connection() as conn:
        assert conn is healthy
    driver.putconn.assert_any_call(stale, close=True)
    driver.putconn.assert_called_with(healthy, close=False)


def test_failed_replacement_does_not_leak_slots(monkeypatch):
    pool, driver, conn = make_pool(monkeypatch, api_db_pool_min=1, api_db_pool_max=1)
    driver.getconn.side_effect = [
        FakeConnection(psycopg2.OperationalError('Lost')),
        FakeConnection(psycopg2.OperationalError('Still lost')),
        conn,
    ]
    with pytest.raises(psycopg2.OperationalError):
        with pool.connection():
            pass
    with pool.connection() as borrowed:
        assert borrowed is conn


def test_connection_failure_during_query_is_not_replayed(monkeypatch):
    pool, driver, conn = make_pool(monkeypatch)
    with pytest.raises(psycopg2.OperationalError):
        with pool.connection():
            raise psycopg2.OperationalError('Connection lost during SQL')
    driver.getconn.assert_called_once()
    driver.putconn.assert_called_once_with(conn, close=True)


def test_exhausted_pool_has_bounded_wait_and_recovers(monkeypatch):
    pool, driver, _ = make_pool(monkeypatch, api_db_pool_min=1, api_db_pool_max=1,
                                 api_db_pool_wait_timeout=0.02)
    entered, release = Event(), Event()

    def hold():
        with pool.connection():
            entered.set()
            assert release.wait(5)

    with ThreadPoolExecutor(max_workers=1) as executor:
        task = executor.submit(hold)
        try:
            assert entered.wait(5)
            with pytest.raises(PoolBusyError):
                with pool.connection():
                    pass
            driver.getconn.assert_called_once()
        finally:
            release.set()
        task.result()
    with pool.connection():
        pass


def test_api_lifespan_pool_query_and_shutdown_without_qwen(monkeypatch):
    config = settings()
    driver = Mock()
    conn = FakeConnection()
    driver.getconn.return_value = conn
    monkeypatch.setattr('app.database.ThreadedConnectionPool', Mock(return_value=driver))
    monkeypatch.setattr('app.main.get_api_settings', lambda: config)
    app.dependency_overrides[get_api_settings] = lambda: config
    try:
        with TestClient(app) as client:
            assert client.get('/health/live').status_code == 200
            assert client.get('/v1/patrons/P001/fortunes/today').status_code == 401
            response = client.get('/v1/patrons/P001/fortunes/2026-11-20', headers={'X-API-Key': 'test'})
            assert response.status_code == 404
            query, args = next((sql, args) for sql, args in conn.queries if 'SELECT payload' in sql)
            assert args[0] == 'P001'
            assert 'fortune_date = %s' in query
            payload = {
                'patron_id': 'P001', 'fortune_date': '2026-11-20',
                'lucky_zodiac': 'Tiger', 'lucky_number': 3,
                'lucky_color': {'name': 'Green', 'hex': '#228B22'},
                'lucky_item': {'id': 'I1', 'name': 'Item', 'metadata': {}},
                'lucky_dining': {'id': 'D1', 'name': 'Dining', 'metadata': {}},
                'generated_at': '2026-11-20T00:00:00Z', 'model': 'Qwen',
                'prompt_version': 'fortune-v6', 'rules_version': 'daily-theme-v8',
                'personalization': 'four_pillars',
            }
            conn.result = (json.dumps(payload),)
            response = client.get('/v1/patrons/P001/fortunes/2026-11-20', headers={'X-API-Key': 'test'})
            assert response.status_code == 200
            assert response.json() == payload
            driver.closeall.assert_not_called()
            driver.getconn.side_effect = PoolBusyError('Busy')
            assert client.get('/v1/patrons/P001/fortunes/today', headers={'X-API-Key': 'test'}).status_code == 503
        driver.closeall.assert_called_once()
        assert not hasattr(app.state, 'database_pool')
    finally:
        app.dependency_overrides.clear()


def test_worker_keeps_standalone_connection_path(monkeypatch):
    conn = FakeConnection()
    connect = Mock(return_value=conn)
    monkeypatch.setattr('app.database.psycopg2.connect', connect)
    with connection(settings()) as borrowed:
        assert borrowed is conn
    assert conn.closed
    assert conn.commits == 1


def test_pool_configuration_validation():
    with pytest.raises(ValidationError):
        settings(api_db_pool_min=5, api_db_pool_max=2)
    with pytest.raises(ValidationError):
        settings(api_db_pool_wait_timeout=0)
