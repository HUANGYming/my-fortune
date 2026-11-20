from contextlib import contextmanager
from threading import BoundedSemaphore
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from app.config import ApiSettings


class PoolBusyError(TimeoutError):
    """No API connection became available within the configured wait time."""


class DatabasePool:
    """One bounded, thread-safe connection pool per API process."""

    def __init__(self, settings: ApiSettings):
        self._slots = BoundedSemaphore(settings.api_db_pool_max)
        self._wait_timeout = settings.api_db_pool_wait_timeout
        self._closed = False
        self._pool = ThreadedConnectionPool(
            settings.api_db_pool_min, settings.api_db_pool_max,
            settings.database_dsn.get_secret_value(), connect_timeout=10,
        )

    def _checkout(self):
        # Check idle connections before reuse; retry once with a fresh connection.
        # Only the health check is retried, never the caller's SQL.
        for attempt in range(2):
            conn = self._pool.getconn()
            try:
                if conn.closed:
                    raise psycopg2.InterfaceError("Connection is closed")
                with conn:
                    with conn.cursor() as cursor:
                        cursor.execute("SELECT 1")
                return conn
            except (psycopg2.InterfaceError, psycopg2.OperationalError):
                self._pool.putconn(conn, close=True)
                if attempt:
                    raise
            except BaseException:
                self._pool.putconn(conn, close=True)
                raise

    @contextmanager
    def connection(self):
        """Borrow, finish the transaction, then return or discard the connection."""
        if self._closed:
            raise RuntimeError("Database pool is closed")
        if not self._slots.acquire(timeout=self._wait_timeout):
            raise PoolBusyError("Database connection pool is busy")
        conn = None
        discard = False
        try:
            conn = self._checkout()
            try:
                with conn:
                    yield conn
            except (psycopg2.InterfaceError, psycopg2.OperationalError):
                discard = True
                raise
        finally:
            try:
                if conn is not None:
                    self._pool.putconn(conn, close=discard or bool(conn.closed))
            finally:
                self._slots.release()

    def close(self):
        """Close the pool after the API has finished serving active requests."""
        if not self._closed:
            self._closed = True
            self._pool.closeall()


@contextmanager
def connection(settings: ApiSettings):
    """Commit on success, roll back on failure, and always close the connection."""
    # Worker connections stay independent of the API's lifespan-managed pool.
    conn = psycopg2.connect(settings.database_dsn.get_secret_value(), connect_timeout=10)
    try:
        with conn:
            yield conn
    finally:
        conn.close()
