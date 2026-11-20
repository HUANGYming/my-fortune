from functools import lru_cache
from pydantic import SecretStr, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Per-batch worker count and per-client limit for in-flight Qwen requests.
CONCURRENCY_LIMIT = 16


class ApiSettings(BaseSettings):
    # Read deployment values from environment variables or the local .env file.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_dsn: SecretStr
    api_key: SecretStr
    api_db_pool_min: int = Field(default=2, ge=1)
    api_db_pool_max: int = Field(default=10, ge=1)
    api_db_pool_wait_timeout: float = Field(default=2, gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_pool_size(self):
        if self.api_db_pool_min > self.api_db_pool_max:
            raise ValueError("API_DB_POOL_MIN must not exceed API_DB_POOL_MAX")
        return self


class Settings(ApiSettings):
    # The calculation worker additionally requires model configuration.
    qwen_base_url: str
    qwen_model: str
    qwen_api_key: SecretStr = SecretStr("")
    request_timeout: float = 90
    prompt_version: str = "fortune-v6"


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_api_settings() -> ApiSettings:
    return ApiSettings()

