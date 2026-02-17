from pydantic import BaseModel


class PayLoanWebhookRequest(BaseModel):
    loan_id: str
    amount_paid: float
    provider_reference: str
    provider_name: str


class PayLoanWebhookResponse(BaseModel):
    status: str
    loan_id: str
