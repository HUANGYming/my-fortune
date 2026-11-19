from functools import lru_cache
from pathlib import Path
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_dsn: SecretStr
    api_key: SecretStr
    qwen_base_url: str
    qwen_model: str
    qwen_api_key: SecretStr = SecretStr("")
    taibu_base_url: str | None = None
    node_binary: str = str(Path(__file__).resolve().parent.parent / "bridge/node_modules/node/bin/node")
    request_timeout: float = 90
    prompt_version: str = "fortune-v3"


@lru_cache
def get_settings() -> Settings:
    return Settings()

