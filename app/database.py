from contextlib import contextmanager
import psycopg2
from app.config import Settings


@contextmanager
def connection(settings: Settings):
    """Commit on success, roll back on failure, and always close the connection."""
    conn = psycopg2.connect(settings.database_dsn.get_secret_value(), connect_timeout=10)
    try:
        with conn:
            yield conn
    finally:
        conn.close()
