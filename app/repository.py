"""Map Yellowbrick rows to domain models and publish complete daily results."""
import json
from datetime import date
from app.config import ApiSettings
from app.database import connection
from app.models import CatalogEntry, Fortune, Patron


class Repository:
    def __init__(self, settings: ApiSettings, connection_factory=None):
        self.settings = settings
        self._connection_factory = connection_factory

    def _connection(self):
        # API injects pooled checkout; workers retain the standalone connection path.
        return self._connection_factory() if self._connection_factory else connection(self.settings)

    def get_patron(self, patron_id: str) -> Patron | None:
        """Read birth inputs from the source table without inventing missing values."""
        with self._connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT patron_id, birth_date, birth_hour, gender, birth_minute, birth_timezone, longitude "
                "FROM fortune_patron_source WHERE patron_id = %s", (patron_id,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return Patron(patron_id=row[0], birth_date=row[1], birth_hour=row[2],
                      gender=row[3], birth_minute=row[4], birth_timezone=row[5], longitude=row[6])

    def iter_patron_ids(self, batch_size: int = 500):
        """Read every distinct Patron ID using bounded keyset pages."""
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        after = None
        while True:
            with self._connection() as conn, conn.cursor() as cursor:
                if after is None:
                    cursor.execute(
                        "SELECT DISTINCT patron_id FROM fortune_patron_source "
                        "ORDER BY patron_id LIMIT %s", (batch_size,),
                    )
                else:
                    cursor.execute(
                        "SELECT DISTINCT patron_id FROM fortune_patron_source "
                        "WHERE patron_id > %s ORDER BY patron_id LIMIT %s", (after, batch_size),
                    )
                rows = cursor.fetchall()
            if not rows:
                return
            for row in rows:
                yield row[0]
            after = rows[-1][0]

    def get_fortune(self, patron_id: str, target_date: date) -> Fortune | None:
        """Read a stored result; a missing row does not trigger generation."""
        with self._connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT payload FROM my_fortunes WHERE patron_id = %s AND fortune_date = %s "
                "ORDER BY generated_at DESC LIMIT 1", (patron_id, target_date),
            )
            row = cursor.fetchone()
        return Fortune.model_validate_json(row[0]) if row else None

    def catalog(self, kind: str) -> list[CatalogEntry]:
        """Load active items or restaurants; rules.py applies element/tag filtering."""
        with self._connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT entry_id, name, metadata_json FROM fortune_catalog "
                "WHERE kind = %s AND active = true ORDER BY entry_id", (kind,),
            )
            return [CatalogEntry(id=row[0], name=row[1], metadata=json.loads(row[2] or "{}"))
                    for row in cursor.fetchall()]

    def save(self, fortune: Fortune, audit: dict) -> None:
        """Publish the result and audit together, preserving any existing success."""
        # Serialize the short publication transaction across writers, including retries.
        # All writers must use this path. Verify LOCK support on the target YB version.
        with self._connection() as conn, conn.cursor() as cursor:
            cursor.execute("LOCK TABLE my_fortunes IN EXCLUSIVE MODE")
            cursor.execute(
                "SELECT 1 FROM my_fortunes WHERE patron_id = %s AND fortune_date = %s",
                (fortune.patron_id, fortune.fortune_date),
            )
            if cursor.fetchone():
                return
            cursor.execute(
                "INSERT INTO my_fortunes "
                "(patron_id, fortune_date, generated_at, payload, audit_json) VALUES (%s,%s,%s,%s,%s)",
                (fortune.patron_id, fortune.fortune_date, fortune.generated_at,
                 fortune.model_dump_json(), json.dumps(audit, ensure_ascii=False)),
            )
