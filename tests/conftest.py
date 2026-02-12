import pytest
from unittest.mock import AsyncMock, Mock

from database.connection import Database
from database.context import connection_context


@pytest.fixture
async def db():
    """Integration test fixture: real DB connection with rollback."""
    test_db = Database()
    await test_db.connect("postgresql://user:pass@localhost:5432/test_loans")

    async with connection_context(test_db) as conn:
        transaction = conn.transaction()
        await transaction.start()
        yield conn
        await transaction.rollback()

    await test_db.disconnect()
