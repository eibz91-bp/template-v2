import pytest
from unittest.mock import AsyncMock, Mock, patch

from entity.loan import Loan
from entity.result import Result
from exception.domain import EntityNotFoundError, InvalidOperationError, AlreadyProcessedError
from use_case.disburse_loan import DisburseLoan


@pytest.fixture
def approved_loan():
    return Loan(
        id="l-1", user_id="u-1", amount=1000.0, status="approved",
        score=750, created_at="2025-01-01"
    )


@patch("use_case.disburse_loan.transaction_context")
async def test_disburse_loan_success(mock_tx, approved_loan):
    mock_tx.return_value.__aenter__ = AsyncMock()
    mock_tx.return_value.__aexit__ = AsyncMock(return_value=False)

    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = approved_loan
    mock_repo.update_status_if.return_value = approved_loan

    mock_provider = AsyncMock()
    mock_provider.execute.return_value = Result(status="disbursed", reference="ref-123")

    mock_factory = Mock()
    mock_factory.get.return_value = mock_provider

    mock_outbox = AsyncMock()

    use_case = DisburseLoan(mock_repo, mock_factory, mock_outbox)
    result = await use_case.execute("l-1", "stp")

    assert result.status == "disbursed"
    assert result.reference == "ref-123"
    mock_factory.get.assert_called_once_with("stp")
    mock_outbox.save.assert_called_once()


@patch("use_case.disburse_loan.transaction_context")
async def test_disburse_loan_not_approved(mock_tx):
    mock_tx.return_value.__aenter__ = AsyncMock()
    mock_tx.return_value.__aexit__ = AsyncMock(return_value=False)

    pending_loan = Loan(
        id="l-1", user_id="u-1", amount=1000.0, status="pending",
        score=None, created_at="2025-01-01"
    )
    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = pending_loan
    mock_factory = Mock()
    mock_outbox = AsyncMock()

    use_case = DisburseLoan(mock_repo, mock_factory, mock_outbox)
    with pytest.raises(InvalidOperationError):
        await use_case.execute("l-1", "stp")


@patch("use_case.disburse_loan.transaction_context")
async def test_disburse_loan_not_found(mock_tx):
    mock_tx.return_value.__aenter__ = AsyncMock()
    mock_tx.return_value.__aexit__ = AsyncMock(return_value=False)

    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = None
    mock_factory = Mock()
    mock_outbox = AsyncMock()

    use_case = DisburseLoan(mock_repo, mock_factory, mock_outbox)
    with pytest.raises(EntityNotFoundError):
        await use_case.execute("l-999", "stp")
