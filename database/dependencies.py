from database.context import connection_context

database = None


async def get_db_connection():
    async with connection_context(database):
        yield
