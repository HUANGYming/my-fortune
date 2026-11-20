import json
from pathlib import Path
import sqlite3
from app.models import CatalogEntry, Fortune, Patron

ROOT = Path(__file__).resolve().parents[1]


def test_seed_is_repeatable_preserves_other_ids_and_has_consistent_results():
    # Local fixture/content check. Yellowbrick connectivity and dialect need live integration.
    connection = sqlite3.connect(':memory:')
    try:
        connection.executescript((ROOT / 'sql/001_schema.sql').read_text())
        connection.execute("INSERT INTO fortune_patron_source (patron_id) VALUES ('EXISTING-PATRON')")
        connection.commit()
        sql = (ROOT / 'sql/003_test_data.sql').read_text()
        connection.executescript(sql)
        connection.executescript(sql)
        assert connection.execute('SELECT COUNT(*) FROM fortune_patron_source').fetchone()[0] == 7
        assert connection.execute('SELECT COUNT(*) FROM fortune_catalog').fetchone()[0] == 20
        assert connection.execute('SELECT COUNT(*) FROM my_fortunes').fetchone()[0] == 10
        assert connection.execute("SELECT COUNT(*) FROM fortune_patron_source WHERE patron_id='EXISTING-PATRON'").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM my_fortunes WHERE patron_id='DEMO-P006'").fetchone()[0] == 0
        patrons = {}
        for row in connection.execute('SELECT patron_id, birth_date, birth_hour, gender, birth_minute, birth_timezone, longitude FROM fortune_patron_source WHERE patron_id != ?', ('EXISTING-PATRON',)):
            patron = Patron(patron_id=row[0], birth_date=row[1], birth_hour=row[2], gender=row[3],
                            birth_minute=row[4], birth_timezone=row[5], longitude=row[6])
            patrons[patron.patron_id] = patron
        catalog = {}
        for row in connection.execute('SELECT kind, entry_id, name, metadata_json, active FROM fortune_catalog'):
            entry = CatalogEntry(id=row[1], name=row[2], metadata=json.loads(row[3]))
            catalog[entry.id] = (row[0], entry, bool(row[4]))
        modes = set()
        for patron_id, target_date, payload, audit_json in connection.execute('SELECT patron_id, fortune_date, payload, audit_json FROM my_fortunes'):
            fortune = Fortune.model_validate_json(payload)
            audit = json.loads(audit_json)
            modes.add(fortune.personalization)
            assert fortune.patron_id == patron_id
            assert fortune.fortune_date.isoformat() == target_date
            assert fortune.model == 'fixture-no-llm'
            assert audit['demo'] is True
            assert audit['facts']['engine']['version'] == '4.1.0'
            for kind, selected in [('item', fortune.lucky_item), ('dining', fortune.lucky_dining)]:
                saved_kind, entry, active = catalog[selected.id]
                assert active and saved_kind == kind
                assert selected.id == entry.id and selected.name == entry.name
                # Published metadata is a snapshot; new zodiac tags do not rewrite history.
                assert all(entry.metadata[key] == value for key, value in selected.metadata.items())
        assert modes == {'general', 'three_pillars', 'four_pillars'}
    finally:
        connection.close()


def test_demo_active_catalog_provides_choices_for_all_five_elements():
    from app.rules import ELEMENTS, rank_catalog

    connection = sqlite3.connect(':memory:')
    try:
        connection.executescript((ROOT / 'sql/001_schema.sql').read_text())
        connection.executescript((ROOT / 'sql/003_test_data.sql').read_text())
        for kind in ('item', 'dining'):
            catalog = [CatalogEntry(id=row[0], name=row[1], metadata=json.loads(row[2])) for row in
                       connection.execute('SELECT entry_id, name, metadata_json FROM fortune_catalog '
                                          'WHERE active = true AND kind = ?', (kind,))]
            for element in ELEMENTS:
                data = {'daily_reading': {'element': element}, 'lucky_zodiac': 'Tiger',
                        'lucky_color': {'name': 'Gold'}}
                candidates = rank_catalog(data, catalog, kind)
                assert len(candidates) >= 2
                assert all(element in entry.metadata['elements'] for entry in candidates)
                assert all(entry.id != 'DEMO-D006' for entry in candidates)
    finally:
        connection.close()
