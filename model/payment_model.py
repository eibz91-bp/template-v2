from sqlalchemy import DateTime, ForeignKey, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from entity.payment import Payment
from model.base import Base


class PaymentModel(Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    loan_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("loans.id"), nullable=False
    )
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    provider_reference: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True
    )
    provider_name: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[str] = mapped_column(
        DateTime, server_default=text("NOW()"), nullable=True
    )

    def to_entity(self) -> Payment:
        return Payment(
            id=str(self.id),
            loan_id=str(self.loan_id),
            amount=float(self.amount),
            provider_reference=self.provider_reference,
            provider_name=self.provider_name,
            created_at=str(self.created_at),
        )
