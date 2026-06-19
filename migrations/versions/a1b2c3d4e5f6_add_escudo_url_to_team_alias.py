"""add_escudo_url_to_team_alias

Revision ID: a1b2c3d4e5f6
Revises: 7b24c90f7905
Create Date: 2026-06-19 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
down_revision = '7b24c90f7905'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'team_alias',
        sa.Column('escudo_url', sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('team_alias', 'escudo_url')
