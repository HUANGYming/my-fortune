import asyncio
from datetime import date
from app.config import Settings
from app.models import Patron
from app.taibu import TaibuClient


def test_native_python_four_pillars_and_unknown_hour():
    settings = Settings(database_dsn='unused', api_key='test', qwen_base_url='http://unused',
                        qwen_model='Qwen')
    patron = Patron(patron_id='P001', birth_date=date(1990, 1, 15), birth_hour=9,
                    birth_timezone='Asia/Shanghai', gender='male')
    client = TaibuClient(settings)
    data = asyncio.run(client.context(patron, date(2026, 11, 20)))
    assert data['engine']['name'] == 'my-fortune-python'
    assert data['personalization'] == 'four_pillars'
    assert len(data['bazi']['四柱']) == 4
    assert data['relations']
    assert data['coordinates']['day_master']
    patron.birth_hour = None
    data = asyncio.run(client.context(patron, date(2026, 11, 20)))
    assert data['personalization'] == 'three_pillars'
    assert len(data['bazi']['四柱']) == 3
    general = asyncio.run(client.context(Patron(patron_id='P002'), date(2026, 11, 20)))
    assert general['personalization'] == 'general'
    assert general['bazi'] is None
