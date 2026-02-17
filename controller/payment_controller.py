from schema.payment_schema import PayLoanWebhookRequest, PayLoanWebhookResponse
from use_case.pay_loan import PayLoan


class PaymentController:
    def __init__(self, pay_loan: PayLoan) -> None:
        self.pay_loan = pay_loan

    async def pay(self, request: PayLoanWebhookRequest) -> PayLoanWebhookResponse:
        loan = await self.pay_loan.execute(
            loan_id=request.loan_id,
            amount=request.amount_paid,
            provider_reference=request.provider_reference,
            provider_name=request.provider_name,
        )
        return PayLoanWebhookResponse(status=loan.status, loan_id=loan.id)
