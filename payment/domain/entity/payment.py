from dataclasses import dataclass


@dataclass
class Payment:
    id: str
    loan_id: str
    amount: float
    provider_reference: str
    provider_name: str
    created_at: str
