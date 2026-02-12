"""create loans table

Revision ID: 002
Revises: 001
Create Date: 2025-01-01
"""
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE loans (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            amount NUMERIC(12,2) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            score INT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_loans_user_id ON loans(user_id)")
    op.execute("CREATE INDEX idx_loans_status ON loans(status)")


def downgrade():
    op.execute("DROP TABLE loans")
