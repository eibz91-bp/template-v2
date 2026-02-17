from fastapi import APIRouter, Depends

from controller.payment_controller import PaymentController
from dependencies.providers import get_payment_controller
from schema.payment_schema import PayLoanWebhookRequest

router = APIRouter()


@router.post("/api/v1/webhooks/payments")
async def pay_loan_webhook(
    body: PayLoanWebhookRequest,
    ctrl: PaymentController = Depends(get_payment_controller),
) -> dict:
    return (await ctrl.pay(body)).model_dump()
