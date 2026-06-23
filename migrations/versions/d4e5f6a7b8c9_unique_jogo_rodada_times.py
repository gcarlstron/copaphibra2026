"""unique constraint em jogos (rodada_id, time_casa, time_visitante)

Revision ID: d4e5f6a7b8c9
Revises: a1b2c3d4e5f6
Create Date: 2026-06-22 18:30:00.000000

Garante a idempotência de jogo no nível do banco (até então só por query no
importador). Modo batch para funcionar tanto no SQLite (recria a tabela) quanto
no Postgres/Neon (ALTER TABLE direto).

ATENÇÃO: se a tabela tiver linhas duplicadas em (rodada_id, time_casa,
time_visitante), a migração falha — dedupe antes de aplicar.
"""
from alembic import op


revision = 'd4e5f6a7b8c9'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("jogos") as batch_op:
        batch_op.create_unique_constraint(
            "uq_jogo_rodada_times",
            ["rodada_id", "time_casa", "time_visitante"],
        )


def downgrade() -> None:
    with op.batch_alter_table("jogos") as batch_op:
        batch_op.drop_constraint("uq_jogo_rodada_times", type_="unique")
