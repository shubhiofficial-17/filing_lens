from psycopg_pool import AsyncConnectionPool


class Database:
    """A small wrapper around a psycopg connection pool."""

    def __init__(self, url: str) -> None:
        self._pool = AsyncConnectionPool(url, min_size=1, max_size=10, open=False)

    async def open(self) -> None:
        await self._pool.open(wait=True, timeout=30)
        # pgvector ships in the image; the extension still has to be enabled once per database.
        async with self._pool.connection() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

    async def close(self) -> None:
        await self._pool.close()

    async def pgvector_version(self) -> str | None:
        async with self._pool.connection(timeout=2) as conn:
            cur = await conn.execute(
                "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
            )
            row = await cur.fetchone()
            return row[0] if row else None
