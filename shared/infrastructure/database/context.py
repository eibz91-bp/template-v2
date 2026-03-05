from contextlib import asynccontextmanager
from contextvars import ContextVar

from sqlalchemy.ext.asyncio import AsyncSession

current_session: ContextVar[AsyncSession] = ContextVar("current_session")


def get_current_session() -> AsyncSession:
    try:
        return current_session.get()
    except LookupError:
        raise RuntimeError(
            "No database session available. "
            "Use 'async with session_context(database)' or "
            "ensure Depends(get_db_connection) is configured."
        )


@asynccontextmanager
async def session_context(database):
    async with database.session_factory() as session:
        token = current_session.set(session)
        try:
            yield session
        finally:
            current_session.reset(token)
