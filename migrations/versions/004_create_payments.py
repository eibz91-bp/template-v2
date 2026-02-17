"""create payments table

Revision ID: 004
Revises: 003
Create Date: 2026-02-17
"""
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE payments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            loan_id UUID NOT NULL REFERENCES loans(id),
            amount NUMERIC(12,2) NOT NULL,
            provider_reference VARCHAR(100) NOT NULL,
            provider_name VARCHAR(50) NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE UNIQUE INDEX idx_payments_provider_reference "
        "ON payments(provider_reference)"
    )
    op.execute("CREATE INDEX idx_payments_loan_id ON payments(loan_id)")


def downgrade():
    op.execute("DROP TABLE payments")
