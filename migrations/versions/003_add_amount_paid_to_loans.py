"""add amount_paid to loans

Revision ID: 003
Revises: 002
Create Date: 2026-02-17
"""
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE loans
        ADD COLUMN amount_paid NUMERIC(12,2) NOT NULL DEFAULT 0
    """)


def downgrade():
    op.execute("ALTER TABLE loans DROP COLUMN amount_paid")
