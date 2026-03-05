from dataclasses import asdict

from loan.infrastructure.http.schema.loan_schema import (
    DisburseLoanRequest,
    DisburseLoanResponse,
    LoanDetailResponse,
    LoanResponse,
    RequestLoanRequest,
)


class LoanController:
    def __init__(self, request_loan, evaluate_loan, disburse_loan, get_loan_detail):
        self.request_loan = request_loan
        self.evaluate_loan = evaluate_loan
        self.disburse_loan = disburse_loan
        self.get_loan_detail = get_loan_detail

    async def request(self, request: RequestLoanRequest):
        loan = await self.request_loan.execute(request.user_id, request.amount)
        return LoanResponse(**asdict(loan))

    async def evaluate(self, loan_id: str):
        loan = await self.evaluate_loan.execute(loan_id)
        return LoanResponse(**asdict(loan))

    async def disburse(self, loan_id: str, request: DisburseLoanRequest):
        result = await self.disburse_loan.execute(loan_id, request.provider)
        return DisburseLoanResponse(status=result.status, reference=result.reference)

    async def detail(self, loan_id: str):
        detail = await self.get_loan_detail.execute(loan_id)
        return LoanDetailResponse.model_validate(detail)
