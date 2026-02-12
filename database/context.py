from contextlib import asynccontextmanager
from contextvars import ContextVar

current_connection: ContextVar = ContextVar("current_connection")


def get_current_connection():
    try:
        return current_connection.get()
    except LookupError:
        raise RuntimeError(
            "No database connection available. "
            "Use 'async with connection_context(database)' or "
            "ensure Depends(get_db_connection) is configured."
        )


@asynccontextmanager
async def connection_context(database):
    async with database.pool.acquire() as conn:
        token = current_connection.set(conn)
        try:
            yield conn
        finally:
            current_connection.reset(token)
