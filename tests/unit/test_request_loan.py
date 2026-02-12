import pytest
from unittest.mock import AsyncMock

from entity.user import User
from entity.loan import Loan
from exception.domain import EntityNotFoundError
from use_case.request_loan import RequestLoan


async def test_request_loan_success():
    mock_user_repo = AsyncMock()
    mock_user_repo.get_by_id.return_value = User(
        id="u-1", email="test@example.com", name="Test", created_at="2025-01-01"
    )

    mock_loan_repo = AsyncMock()
    mock_loan_repo.create.return_value = Loan(
        id="l-1", user_id="u-1", amount=1000.0, status="pending",
        score=None, created_at="2025-01-01"
    )

    use_case = RequestLoan(mock_user_repo, mock_loan_repo)
    result = await use_case.execute.__wrapped__(use_case, "u-1", 1000.0)

    assert result.id == "l-1"
    assert result.status == "pending"
    mock_loan_repo.create.assert_called_once_with("u-1", 1000.0)


async def test_request_loan_user_not_found():
    mock_user_repo = AsyncMock()
    mock_user_repo.get_by_id.return_value = None
    mock_loan_repo = AsyncMock()

    use_case = RequestLoan(mock_user_repo, mock_loan_repo)
    with pytest.raises(EntityNotFoundError):
        await use_case.execute.__wrapped__(use_case, "u-999", 1000.0)
