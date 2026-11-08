from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings come from environment variables prefixed with FILINGLENS_."""

    model_config = SettingsConfigDict(env_prefix="FILINGLENS_", env_file=".env", extra="ignore")

    # postgresql://user:password@host:5432/db. Without it the API uses an in-memory store and
    # reports "not ready", because nothing it holds survives a restart.
    database_url: str | None = None

    # Load the fictional fixture filings when the store is empty.
    seed_fixtures: bool = True

    # SEC asks every client to identify itself, e.g. "FilingLens you@example.com".
    edgar_user_agent: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
