from functools import lru_cache
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


CONCURRENCY_LIMIT = 16


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_dsn: SecretStr
    api_key: SecretStr
    qwen_base_url: str
    qwen_model: str
    qwen_api_key: SecretStr = SecretStr("")
    request_timeout: float = 90
    prompt_version: str = "fortune-v5"


@lru_cache
def get_settings() -> Settings:
    return Settings()

