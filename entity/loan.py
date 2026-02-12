from dataclasses import dataclass


@dataclass
class Loan:
    id: str
    user_id: str
    amount: float
    status: str
    score: int | None
    created_at: str

    @classmethod
    def from_record(cls, record):
        return cls(
            id=str(record["id"]),
            user_id=str(record["user_id"]),
            amount=float(record["amount"]),
            status=record["status"],
            score=record["score"],
            created_at=str(record["created_at"]),
        )
