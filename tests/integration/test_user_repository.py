import pytest

from repository.user_repository import UserRepository
from exception.domain import AlreadyExistsError


@pytest.mark.usefixtures("db")
async def test_create_and_get_user(db):
    repo = UserRepository()

    user = await repo.create("integration@test.com", "Integration Test")
    assert user.email == "integration@test.com"
    assert user.name == "Integration Test"
    assert user.id is not None

    fetched = await repo.get_by_id(user.id)
    assert fetched is not None
    assert fetched.email == "integration@test.com"


@pytest.mark.usefixtures("db")
async def test_get_user_by_email(db):
    repo = UserRepository()

    await repo.create("find@test.com", "Find Me")
    found = await repo.get_by_email("find@test.com")

    assert found is not None
    assert found.name == "Find Me"


@pytest.mark.usefixtures("db")
async def test_create_duplicate_email(db):
    repo = UserRepository()

    await repo.create("dup@test.com", "First")
    with pytest.raises(AlreadyExistsError):
        await repo.create("dup@test.com", "Second")


@pytest.mark.usefixtures("db")
async def test_get_nonexistent_user(db):
    repo = UserRepository()
    result = await repo.get_by_id("00000000-0000-0000-0000-000000000000")
    assert result is None
