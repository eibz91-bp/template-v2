import pytest

from shared.infrastructure.database.connection import Database
from shared.infrastructure.database.context import session_context


@pytest.fixture
async def db():
    """Integration test fixture: real DB session with rollback."""
    test_db = Database()
    await test_db.connect(
        "postgresql://user:pass@localhost:5432/test_loans"
    )

    async with session_context(test_db) as session:
        yield session
        await session.rollback()

    await test_db.disconnect()
