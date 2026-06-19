"""add_sync_state_and_team_alias

Revision ID: 7b24c90f7905
Revises: 0439d0e80604
Create Date: 2026-06-19 09:44:06.221873

"""
from alembic import op
import sqlalchemy as sa


revision = '7b24c90f7905'
down_revision = '0439d0e80604'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sync_state",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("chave", sa.String(length=80), nullable=False),
        sa.Column("ultima_execucao", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f("ix_sync_state_chave"), "sync_state", ["chave"], unique=True)

    op.create_table(
        "team_alias",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("abreviacao", sa.String(length=10), nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("nome_en", sa.String(length=120), nullable=False),
    )
    op.create_index(op.f("ix_team_alias_abreviacao"), "team_alias", ["abreviacao"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_team_alias_abreviacao"), table_name="team_alias")
    op.drop_table("team_alias")

    op.drop_index(op.f("ix_sync_state_chave"), table_name="sync_state")
    op.drop_table("sync_state")
