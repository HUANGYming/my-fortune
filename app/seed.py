"""Load synthetic inputs, with optional real Qwen generation and persistence."""
import argparse
import asyncio
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import psycopg2
from app.config import get_settings
from app.precalculate import run


def seed_sql(with_llm: bool) -> str:
    script = Path(__file__).resolve().parent.parent / "sql" / "003_test_data.sql"
    sql = script.read_text()
    if with_llm:
        # Preserve previously published fortunes; only load Patron and catalog inputs.
        sql = sql.split("-- BEGIN PRECOMPUTED FIXTURES", 1)[0]
        sql = "\n".join(line for line in sql.splitlines()
                        if not line.startswith("DELETE FROM my_fortunes "))
        sql += "\nCOMMIT;\n"
    return sql


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-llm", action="store_true", help="Generate real fortunes using Qwen")
    parser.add_argument("--date", type=date.fromisoformat, help="Target Macau date, defaults to today")
    args = parser.parse_args()
    if args.date and not args.with_llm:
        parser.error("--date requires --with-llm")
    settings = get_settings()
    connection = psycopg2.connect(settings.database_dsn.get_secret_value(), connect_timeout=10)
    try:
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute(seed_sql(args.with_llm))
    finally:
        connection.close()
    if args.with_llm:
        target_date = args.date or datetime.now(ZoneInfo("Asia/Macau")).date()
        failures = asyncio.run(run(target_date))
        print(f"Full-table generation finished for {target_date}. Failures: {failures}; saved results are reused.")
        raise SystemExit(1 if failures else 0)
    print("Loaded 6 demo Patrons, 12 catalog entries and 10 fixture fortunes.")


if __name__ == "__main__":
    main()
