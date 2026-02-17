from fastapi import Request

from database.context import session_context


async def get_db_connection(request: Request):
    async with session_context(request.app.state.database):
        yield
