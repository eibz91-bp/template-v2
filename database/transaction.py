from contextlib import asynccontextmanager
from functools import wraps

from database.context import get_current_connection


@asynccontextmanager
async def transaction_context():
    conn = get_current_connection()
    async with conn.transaction():
        yield


def transactional(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        conn = get_current_connection()
        async with conn.transaction():
            return await func(*args, **kwargs)
    return wrapper
