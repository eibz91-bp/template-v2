import asyncpg


class Database:
    def __init__(self):
        self.pool = None

    async def connect(self, database_url, min_size=5, max_size=20):
        self.pool = await asyncpg.create_pool(
            database_url,
            min_size=min_size,
            max_size=max_size,
        )

    async def disconnect(self):
        await self.pool.close()
