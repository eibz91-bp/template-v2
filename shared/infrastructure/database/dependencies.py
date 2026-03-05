from fastapi import Request

from shared.infrastructure.database.context import session_context


async def get_db_connection(request: Request):
    async with session_context(request.app.state.database):
        yield
