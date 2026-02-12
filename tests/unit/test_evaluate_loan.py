import pytest
from unittest.mock import AsyncMock, patch

from entity.loan import Loan
from exception.domain import EntityNotFoundError, AlreadyProcessedError
from use_case.evaluate_loan import EvaluateLoan


@pytest.fixture
def loan():
    return Loan(
        id="l-1", user_id="u-1", amount=1000.0, status="pending",
        score=None, created_at="2025-01-01"
    )


@patch("use_case.evaluate_loan.transaction_context")
async def test_evaluate_loan_approved(mock_tx, loan):
    mock_tx.return_value.__aenter__ = AsyncMock()
    mock_tx.return_value.__aexit__ = AsyncMock(return_value=False)

    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = loan
    mock_repo.update_status_if.return_value = loan
    evaluated_loan = Loan(
        id="l-1", user_id="u-1", amount=1000.0, status="approved",
        score=750, created_at="2025-01-01"
    )
    mock_repo.save_evaluation.return_value = evaluated_loan

    mock_scorer = AsyncMock()
    mock_scorer.get_score.return_value = 750

    use_case = EvaluateLoan(mock_repo, mock_scorer, min_score=600)
    result = await use_case.execute("l-1")

    assert result.status == "approved"
    assert result.score == 750
    mock_repo.save_evaluation.assert_called_once_with("l-1", 750, "approved")


@patch("use_case.evaluate_loan.transaction_context")
async def test_evaluate_loan_rejected(mock_tx, loan):
    mock_tx.return_value.__aenter__ = AsyncMock()
    mock_tx.return_value.__aexit__ = AsyncMock(return_value=False)

    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = loan
    mock_repo.update_status_if.return_value = loan
    rejected_loan = Loan(
        id="l-1", user_id="u-1", amount=1000.0, status="rejected",
        score=400, created_at="2025-01-01"
    )
    mock_repo.save_evaluation.return_value = rejected_loan

    mock_scorer = AsyncMock()
    mock_scorer.get_score.return_value = 400

    use_case = EvaluateLoan(mock_repo, mock_scorer, min_score=600)
    result = await use_case.execute("l-1")

    assert result.status == "rejected"
    mock_repo.save_evaluation.assert_called_once_with("l-1", 400, "rejected")


@patch("use_case.evaluate_loan.transaction_context")
async def test_evaluate_loan_not_found(mock_tx):
    mock_tx.return_value.__aenter__ = AsyncMock()
    mock_tx.return_value.__aexit__ = AsyncMock(return_value=False)

    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = None

    mock_scorer = AsyncMock()

    use_case = EvaluateLoan(mock_repo, mock_scorer, min_score=600)
    with pytest.raises(EntityNotFoundError):
        await use_case.execute("l-999")
