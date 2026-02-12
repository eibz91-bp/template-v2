from unittest.mock import AsyncMock, Mock

from entity.loan import Loan
from entity.result import Result
from controller.loan_controller import LoanController
from schema.loan_schema import RequestLoanRequest, DisburseLoanRequest


async def test_loan_controller_request():
    mock_request_loan = AsyncMock()
    mock_request_loan.execute.return_value = Loan(
        id="l-1", user_id="u-1", amount=1000.0, status="pending",
        score=None, created_at="2025-01-01"
    )

    controller = LoanController(mock_request_loan, AsyncMock(), AsyncMock(), AsyncMock())
    response = await controller.request(
        RequestLoanRequest(user_id="u-1", amount=1000.0)
    )

    assert response.id == "l-1"
    assert response.status == "pending"


async def test_loan_controller_evaluate():
    mock_evaluate = AsyncMock()
    mock_evaluate.execute.return_value = Loan(
        id="l-1", user_id="u-1", amount=1000.0, status="approved",
        score=750, created_at="2025-01-01"
    )

    controller = LoanController(AsyncMock(), mock_evaluate, AsyncMock(), AsyncMock())
    response = await controller.evaluate("l-1")

    assert response.status == "approved"
    assert response.score == 750


async def test_loan_controller_disburse():
    mock_disburse = AsyncMock()
    mock_disburse.execute.return_value = Result(status="disbursed", reference="ref-123")

    controller = LoanController(AsyncMock(), AsyncMock(), mock_disburse, AsyncMock())
    response = await controller.disburse(
        "l-1", DisburseLoanRequest(provider="stp")
    )

    assert response.status == "disbursed"
    assert response.reference == "ref-123"


async def test_loan_controller_detail():
    mock_detail = AsyncMock()
    mock_detail.execute.return_value = {
        "id": "l-1", "amount": 1000.0, "status": "disbursed",
        "score": 750, "user_name": "Test", "user_email": "test@example.com",
    }

    controller = LoanController(AsyncMock(), AsyncMock(), AsyncMock(), mock_detail)
    response = await controller.detail("l-1")

    assert response.user_name == "Test"
    assert response.status == "disbursed"
