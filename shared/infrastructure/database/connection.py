from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


class Database:
    def __init__(self):
        self.engine = None
        self.session_factory = None

    async def connect(self, database_url: str, min_size: int = 5, max_size: int = 20):
        url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        self.engine = create_async_engine(
            url,
            pool_size=min_size,
            max_overflow=max_size - min_size,
        )
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def disconnect(self):
        await self.engine.dispose()
