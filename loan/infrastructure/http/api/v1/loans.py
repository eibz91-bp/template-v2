from fastapi import APIRouter, Depends

from loan.infrastructure.http.controller.loan_controller import LoanController
from dependencies.providers import get_loan_controller
from loan.infrastructure.http.schema.loan_schema import DisburseLoanRequest, RequestLoanRequest

router = APIRouter()


@router.post("/loans")
async def request_loan_endpoint(
    body: RequestLoanRequest,
    ctrl: LoanController = Depends(get_loan_controller),
):
    return await ctrl.request(body)


@router.post("/loans/{loan_id}/evaluate")
async def evaluate_loan_endpoint(
    loan_id: str,
    ctrl: LoanController = Depends(get_loan_controller),
):
    return await ctrl.evaluate(loan_id)


@router.post("/loans/{loan_id}/disburse")
async def disburse_loan_endpoint(
    loan_id: str,
    body: DisburseLoanRequest,
    ctrl: LoanController = Depends(get_loan_controller),
):
    return await ctrl.disburse(loan_id, body)


@router.get("/loans/{loan_id}")
async def get_loan_detail_endpoint(
    loan_id: str,
    ctrl: LoanController = Depends(get_loan_controller),
):
    return await ctrl.detail(loan_id)
