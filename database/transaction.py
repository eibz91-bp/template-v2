from contextlib import asynccontextmanager

from database.context import get_current_session


@asynccontextmanager
async def transaction_context():
    session = get_current_session()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
