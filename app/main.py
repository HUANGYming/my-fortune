"""Expose authenticated REST reads of precomputed fortunes and a liveness endpoint."""
from datetime import date, datetime
from contextlib import asynccontextmanager
import asyncio
import logging
import secrets
from zoneinfo import ZoneInfo
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import APIKeyHeader
from app.config import ApiSettings, get_api_settings
from app.database import DatabasePool
from app.models import Fortune
from app.repository import Repository

@asynccontextmanager
async def lifespan(application: FastAPI):
    # Each server process owns its pool; no Qwen configuration is required here.
    pool = await asyncio.to_thread(DatabasePool, get_api_settings())
    application.state.database_pool = pool
    try:
        yield
    finally:
        await asyncio.to_thread(pool.close)
        del application.state.database_pool


app = FastAPI(title="My Fortune API", version="0.1.0", lifespan=lifespan)
key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
logger = logging.getLogger(__name__)


def authorize(key: str | None = Depends(key_header), settings: ApiSettings = Depends(get_api_settings)):
    if key is None or not secrets.compare_digest(key, settings.api_key.get_secret_value()):
        raise HTTPException(status_code=401, detail="Invalid API key")


def repository(request: Request, settings: ApiSettings = Depends(get_api_settings)) -> Repository:
    return Repository(settings, connection_factory=request.app.state.database_pool.connection)


@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/v1/patrons/{patron_id}/fortunes/today", response_model=Fortune,
         dependencies=[Depends(authorize)])
def today(patron_id: str, repo: Repository = Depends(repository)):
    # Resolve "today" in Macau time and reuse the dated lookup path.
    return read_fortune(patron_id, datetime.now(ZoneInfo("Asia/Macau")).date(), repo)


@app.get("/v1/patrons/{patron_id}/fortunes/{fortune_date}", response_model=Fortune,
         dependencies=[Depends(authorize)], responses={404: {"description": "Result not calculated"}})
def read_fortune(patron_id: str, fortune_date: date, repo: Repository = Depends(repository)):
    # API reads never calculate fortunes or call Qwen; the batch job publishes them.
    try:
        result = repo.get_fortune(patron_id, fortune_date)
    except Exception:
        logger.exception("Fortune lookup failed")
        raise HTTPException(status_code=503, detail="Fortune store unavailable") from None
    if result is None:
        raise HTTPException(status_code=404, detail="Fortune not calculated")
    return result
