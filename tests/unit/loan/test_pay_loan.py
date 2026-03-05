import pytest
from unittest.mock import AsyncMock, patch

from loan.domain.entity.loan import Loan
from payment.domain.entity.payment import Payment
from shared.domain.exception.domain import (
    AlreadyProcessedError,
    EntityNotFoundError,
    InvalidOperationError,
)
from loan.application.use_case.pay_loan import PayLoan


def _loan(status: str = "disbursed", amount_paid: float = 0.0) -> Loan:
    return Loan(
        id="l-1",
        user_id="u-1",
        amount=1000.0,
        status=status,
        score=750,
        created_at="2025-01-01",
        amount_paid=amount_paid,
    )


def _payment() -> Payment:
    return Payment(
        id="p-1",
        loan_id="l-1",
        amount=1000.0,
        provider_reference="ref-1",
        provider_name="stripe",
        created_at="2025-01-01",
    )


def _updated_loan(status: str, amount_paid: float) -> Loan:
    return Loan(
        id="l-1",
        user_id="u-1",
        amount=1000.0,
        status=status,
        score=750,
        created_at="2025-01-01",
        amount_paid=amount_paid,
    )


@patch("loan.application.use_case.pay_loan.transaction_context")
async def test_full_payment_marks_loan_as_paid(mock_tx):
    mock_tx.return_value.__aenter__ = AsyncMock()
    mock_tx.return_value.__aexit__ = AsyncMock(return_value=False)

    loan_repo = AsyncMock()
    loan_repo.get_by_id.return_value = _loan("disbursed", 0.0)
    loan_repo.apply_payment.return_value = _updated_loan("paid", 1000.0)

    payment_repo = AsyncMock()
    payment_repo.create.return_value = _payment()

    uc = PayLoan(loan_repo, payment_repo)
    result = await uc.execute("l-1", 1000.0, "ref-1", "stripe")

    assert result.status == "paid"
    assert result.amount_paid == 1000.0
    payment_repo.create.assert_called_once_with("l-1", 1000.0, "ref-1", "stripe")
    loan_repo.apply_payment.assert_called_once_with("l-1", 1000.0, "paid")


@patch("loan.application.use_case.pay_loan.transaction_context")
async def test_partial_payment_marks_loan_as_partially_paid(mock_tx):
    mock_tx.return_value.__aenter__ = AsyncMock()
    mock_tx.return_value.__aexit__ = AsyncMock(return_value=False)

    loan_repo = AsyncMock()
    loan_repo.get_by_id.return_value = _loan("disbursed", 0.0)
    loan_repo.apply_payment.return_value = _updated_loan("partially_paid", 500.0)

    payment_repo = AsyncMock()
    payment_repo.create.return_value = _payment()

    uc = PayLoan(loan_repo, payment_repo)
    result = await uc.execute("l-1", 500.0, "ref-1", "stripe")

    assert result.status == "partially_paid"
    loan_repo.apply_payment.assert_called_once_with("l-1", 500.0, "partially_paid")


@patch("loan.application.use_case.pay_loan.transaction_context")
async def test_loan_not_found_raises(mock_tx):
    mock_tx.return_value.__aenter__ = AsyncMock()
    mock_tx.return_value.__aexit__ = AsyncMock(return_value=False)

    loan_repo = AsyncMock()
    loan_repo.get_by_id.return_value = None
    payment_repo = AsyncMock()

    uc = PayLoan(loan_repo, payment_repo)
    with pytest.raises(EntityNotFoundError):
        await uc.execute("l-999", 100.0, "ref-1", "stripe")


@patch("loan.application.use_case.pay_loan.transaction_context")
async def test_invalid_status_raises(mock_tx):
    mock_tx.return_value.__aenter__ = AsyncMock()
    mock_tx.return_value.__aexit__ = AsyncMock(return_value=False)

    loan_repo = AsyncMock()
    loan_repo.get_by_id.return_value = _loan("pending")
    payment_repo = AsyncMock()

    uc = PayLoan(loan_repo, payment_repo)
    with pytest.raises(InvalidOperationError):
        await uc.execute("l-1", 100.0, "ref-1", "stripe")


@patch("loan.application.use_case.pay_loan.transaction_context")
async def test_overpayment_raises(mock_tx):
    mock_tx.return_value.__aenter__ = AsyncMock()
    mock_tx.return_value.__aexit__ = AsyncMock(return_value=False)

    loan_repo = AsyncMock()
    loan_repo.get_by_id.return_value = _loan("disbursed", 0.0)
    payment_repo = AsyncMock()

    uc = PayLoan(loan_repo, payment_repo)
    with pytest.raises(InvalidOperationError, match="exceeds remaining"):
        await uc.execute("l-1", 1500.0, "ref-1", "stripe")


@patch("loan.application.use_case.pay_loan.transaction_context")
async def test_duplicate_provider_reference_raises(mock_tx):
    mock_tx.return_value.__aenter__ = AsyncMock()
    mock_tx.return_value.__aexit__ = AsyncMock(return_value=False)

    loan_repo = AsyncMock()
    loan_repo.get_by_id.return_value = _loan("disbursed", 0.0)

    payment_repo = AsyncMock()
    payment_repo.create.side_effect = AlreadyProcessedError(
        "Payment with reference 'ref-1' already processed"
    )

    uc = PayLoan(loan_repo, payment_repo)
    with pytest.raises(AlreadyProcessedError):
        await uc.execute("l-1", 500.0, "ref-1", "stripe")
