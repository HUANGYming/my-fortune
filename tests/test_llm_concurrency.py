import asyncio
import httpx
from pydantic import BaseModel
from app.config import Settings
from app.llm import QwenClient


class Answer(BaseModel):
    value: int


def test_qwen_http_limit_and_slot_release_after_failure(monkeypatch):
    async def exercise():
        active = 0
        peak = 0
        count = 0
        gate = asyncio.Event()

        async def respond(request):
            nonlocal active, peak, count
            active += 1
            count += 1
            number = count
            peak = max(peak, active)
            if active == 16:
                gate.set()
            try:
                await asyncio.wait_for(gate.wait(), timeout=5)
                await asyncio.sleep(0)
                if number == 1:
                    return httpx.Response(400, json={'error': 'Invalid test request'})
                return httpx.Response(200, json={'choices': [{'message': {'content': '{"value": 1}'}}]})
            finally:
                active -= 1

        client_class = httpx.AsyncClient
        transport = httpx.MockTransport(respond)
        monkeypatch.setattr('app.llm.httpx.AsyncClient',
                            lambda **kwargs: client_class(transport=transport, **kwargs))
        settings = Settings(database_dsn='unused',api_key='test',qwen_base_url='http://qwen/v1',qwen_model='Qwen')
        client = QwenClient(settings)
        results = await asyncio.gather(
            *(client.generate('test', {}, Answer) for _ in range(65)), return_exceptions=True,
        )
        assert peak == 16
        assert active == 0
        assert count == 65
        assert sum(isinstance(result, Answer) for result in results) == 64
        assert sum(isinstance(result, httpx.HTTPStatusError) for result in results) == 1
        # The failure released its slot, so the client remains usable.
        assert (await client.generate('test', {}, Answer)).value == 1

    asyncio.run(exercise())
