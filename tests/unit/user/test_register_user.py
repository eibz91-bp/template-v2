import pytest
from unittest.mock import AsyncMock

from user.domain.entity.user import User
from shared.domain.exception.domain import AlreadyExistsError
from user.application.use_case.register_user import RegisterUser


async def test_register_user_success():
    mock_repo = AsyncMock()
    mock_repo.get_by_email.return_value = None
    mock_repo.create.return_value = User(
        id="u-1", email="test@example.com", name="Test User", created_at="2025-01-01"
    )

    use_case = RegisterUser(mock_repo)
    result = await use_case.execute.__wrapped__(use_case, "test@example.com", "Test User")

    assert result.id == "u-1"
    assert result.email == "test@example.com"
    mock_repo.create.assert_called_once_with("test@example.com", "Test User")


async def test_register_user_already_exists():
    mock_repo = AsyncMock()
    mock_repo.get_by_email.return_value = User(
        id="u-1", email="test@example.com", name="Test User", created_at="2025-01-01"
    )

    use_case = RegisterUser(mock_repo)
    with pytest.raises(AlreadyExistsError):
        await use_case.execute.__wrapped__(use_case, "test@example.com", "Test User")
