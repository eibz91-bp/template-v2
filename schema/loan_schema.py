from pydantic import BaseModel


class RequestLoanRequest(BaseModel):
    user_id: str
    amount: float


class DisburseLoanRequest(BaseModel):
    provider: str


class LoanResponse(BaseModel):
    id: str
    user_id: str
    amount: float
    status: str
    score: int | None = None


class LoanDetailResponse(BaseModel):
    id: str
    amount: float
    status: str
    score: int | None = None
    user_name: str
    user_email: str


class DisburseLoanResponse(BaseModel):
    status: str
    reference: str | None = None
