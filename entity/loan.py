from dataclasses import dataclass

from exception.domain import InvalidOperationError


@dataclass
class Loan:
    id: str
    user_id: str
    amount: float
    status: str
    score: int | None
    created_at: str
    amount_paid: float = 0.0

    def ensure_can_evaluate(self):
        if self.status != "pending":
            raise InvalidOperationError(
                f"Cannot evaluate loan in '{self.status}' status, expected 'pending'"
            )

    def ensure_can_disburse(self):
        if self.status != "approved":
            raise InvalidOperationError(
                f"Cannot disburse loan in '{self.status}' status, expected 'approved'"
            )

    def ensure_can_pay(self) -> None:
        allowed = ("disbursed", "partially_paid")
        if self.status not in allowed:
            raise InvalidOperationError(
                f"Cannot pay loan in '{self.status}' status"
            )

    def determine_evaluation_status(self, score: int, min_score: int) -> str:
        return "approved" if score >= min_score else "rejected"

    def apply_payment(self, amount: float) -> str:
        remaining = self.amount - self.amount_paid
        if amount > remaining:
            raise InvalidOperationError(
                f"Payment {amount} exceeds remaining balance {remaining}"
            )
        if amount == remaining:
            return "paid"
        return "partially_paid"
