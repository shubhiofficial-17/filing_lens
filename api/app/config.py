from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings come from environment variables prefixed with FILINGLENS_."""

    model_config = SettingsConfigDict(env_prefix="FILINGLENS_", env_file=".env", extra="ignore")

    # postgresql://user:password@host:5432/db. Without it the API starts but is not ready.
    database_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
