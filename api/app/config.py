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

    # Chat model: any OpenAI-compatible endpoint, usually the LLM Gateway. Unset = demo model.
    llm_base_url: str | None = None
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    # The router sends hard questions here. Unset = always use llm_model.
    llm_strong_model: str | None = None

    # Embeddings: an OpenAI-compatible /embeddings endpoint. Unset = offline hashing embedder.
    embeddings_base_url: str | None = None
    embeddings_api_key: str = ""
    embeddings_model: str = "text-embedding-3-small"
    embedding_dim: int = 256

    top_k: int = 5

    # How the MCP agent reaches its tools: "stdio" (starts the MCP server as a subprocess),
    # "http" (FILINGLENS_MCP_URL, e.g. http://mcp:8001/mcp) or "direct" (in-process calls).
    mcp_transport: str = "stdio"
    mcp_url: str | None = None

    # Requests per minute per client IP; 0 turns a limit off.
    rate_limit_ask: int = 30
    rate_limit_ingest: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
