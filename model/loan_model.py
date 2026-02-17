from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from entity.loan import Loan
from model.base import Base


class LoanModel(Base):
    __tablename__ = "loans"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=False
    )
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'pending'")
    )
    amount_paid: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=text("0")
    )
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[str] = mapped_column(
        DateTime, server_default=text("NOW()"), nullable=True
    )

    def to_entity(self) -> Loan:
        return Loan(
            id=str(self.id),
            user_id=str(self.user_id),
            amount=float(self.amount),
            status=self.status,
            score=self.score,
            created_at=str(self.created_at),
            amount_paid=float(self.amount_paid),
        )
