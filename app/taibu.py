import asyncio
import json
from datetime import date
from pathlib import Path
import httpx
from app.models import Patron
from app.config import Settings

BRIDGE = Path(__file__).resolve().parent.parent / "bridge" / "context.mjs"


class TaibuClient:
    """Use the vendored core locally, or the same contract on an internal HTTP service."""

    def __init__(self, settings: Settings):
        self.settings = settings

    async def context(self, patron: Patron, target_date: date) -> dict:
        if patron.birth_date and target_date < patron.birth_date:
            raise ValueError("Fortune date precedes birth date")
        payload = {"patron": patron.model_dump(mode="json", exclude={"patron_id", "preferences"}),
                   "date": target_date.isoformat(), "timezone": "Asia/Macau"}
        if self.settings.taibu_base_url:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout) as client:
                response = await client.post(self.settings.taibu_base_url.rstrip("/") + "/context", json=payload)
                response.raise_for_status()
                data = response.json()
        else:
            process = await asyncio.create_subprocess_exec(
                self.settings.node_binary, str(BRIDGE), stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(json.dumps(payload).encode()), self.settings.request_timeout,
                )
            except BaseException:
                if process.returncode is None:
                    process.kill()
                await process.wait()
                raise
            if process.returncode:
                raise ValueError("Taibu calculation failed: " + stderr.decode()[:500])
            data = json.loads(stdout)
        if not isinstance(data, dict) or not data.get("almanac") or not data.get("coordinates"):
            raise ValueError("Taibu must return almanac and normalized coordinates")
        return data
