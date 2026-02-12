"""create outbox table

Revision ID: 003
Revises: 002
Create Date: 2025-01-01
"""
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE outbox (
            id SERIAL PRIMARY KEY,
            destination VARCHAR(100) NOT NULL,
            payload JSONB NOT NULL,
            status VARCHAR(20) DEFAULT 'pending',
            retry_count INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW(),
            sent_at TIMESTAMP
        )
    """)
    op.execute("CREATE INDEX idx_outbox_status ON outbox(status)")


def downgrade():
    op.execute("DROP TABLE outbox")
