from datetime import date, datetime
import logging
import secrets
from zoneinfo import ZoneInfo
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import APIKeyHeader
from app.config import Settings, get_settings
from app.models import Fortune
from app.repository import Repository

app = FastAPI(title="My Fortune API", version="0.1.0")
key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
logger = logging.getLogger(__name__)


def authorize(key: str | None = Depends(key_header), settings: Settings = Depends(get_settings)):
    if key is None or not secrets.compare_digest(key, settings.api_key.get_secret_value()):
        raise HTTPException(status_code=401, detail="Invalid API key")


def repository(settings: Settings = Depends(get_settings)) -> Repository:
    return Repository(settings)


@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/v1/patrons/{patron_id}/fortunes/today", response_model=Fortune,
         dependencies=[Depends(authorize)])
def today(patron_id: str, repo: Repository = Depends(repository)):
    return read_fortune(patron_id, datetime.now(ZoneInfo("Asia/Macau")).date(), repo)


@app.get("/v1/patrons/{patron_id}/fortunes/{fortune_date}", response_model=Fortune,
         dependencies=[Depends(authorize)], responses={404: {"description": "Result not calculated"}})
def read_fortune(patron_id: str, fortune_date: date, repo: Repository = Depends(repository)):
    try:
        result = repo.get_fortune(patron_id, fortune_date)
    except Exception:
        logger.exception("Fortune lookup failed")
        raise HTTPException(status_code=503, detail="Fortune store unavailable") from None
    if result is None:
        raise HTTPException(status_code=404, detail="Fortune not calculated")
    return result
