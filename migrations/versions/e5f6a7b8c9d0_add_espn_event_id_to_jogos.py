"""add espn_event_id to jogos

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-27 12:00:00.000000

Adiciona `espn_event_id` à tabela jogos — identificador estável do evento na
ESPN (ex.: "760486"). Usado no mata-mata para get-or-create por ID em vez de
por par de times, preservando palpites quando um placeholder vira time real.

Nullable: jogos da fase de grupos importados da planilha ficam NULL (ok —
múltiplos NULL não violam UNIQUE no SQLite nem no Postgres).

Modo batch (SQLite recria a tabela; Postgres faz ALTER TABLE direto).
"""
from alembic import op
import sqlalchemy as sa


revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("jogos") as batch_op:
        batch_op.add_column(
            sa.Column("espn_event_id", sa.String(32), nullable=True)
        )
        batch_op.create_unique_constraint(
            "uq_jogo_espn_event_id", ["espn_event_id"]
        )
        batch_op.create_index(
            "ix_jogos_espn_event_id", ["espn_event_id"], unique=True
        )


def downgrade() -> None:
    with op.batch_alter_table("jogos") as batch_op:
        batch_op.drop_index("ix_jogos_espn_event_id")
        batch_op.drop_constraint("uq_jogo_espn_event_id", type_="unique")
        batch_op.drop_column("espn_event_id")
