"""initial schema

Revision ID: 0439d0e80604
Revises: 
Create Date: 2026-06-18 11:43:15.551691

"""
from alembic import op
import sqlalchemy as sa


revision = '0439d0e80604'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rodadas",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("aberta", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("abertura", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fechamento", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f("ix_rodadas_ordem"), "rodadas", ["ordem"], unique=True)

    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("senha_hash", sa.String(length=255), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.UniqueConstraint("username", name="uq_usuarios_username"),
    )
    op.create_index(op.f("ix_usuarios_username"), "usuarios", ["username"], unique=True)

    op.create_table(
        "jogos",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("rodada_id", sa.Integer(), nullable=False),
        sa.Column("data_hora", sa.DateTime(timezone=True), nullable=False),
        sa.Column("time_casa", sa.String(length=120), nullable=False),
        sa.Column("time_visitante", sa.String(length=120), nullable=False),
        sa.Column("gols_casa", sa.Integer(), nullable=True),
        sa.Column("gols_visitante", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="agendado"),
        sa.ForeignKeyConstraint(["rodada_id"], ["rodadas.id"]),
    )
    op.create_index(op.f("ix_jogos_data_hora"), "jogos", ["data_hora"], unique=False)
    op.create_index(op.f("ix_jogos_rodada_id"), "jogos", ["rodada_id"], unique=False)

    op.create_table(
        "palpites",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("jogo_id", sa.Integer(), nullable=False),
        sa.Column("gols_casa", sa.Integer(), nullable=False),
        sa.Column("gols_visitante", sa.Integer(), nullable=False),
        sa.Column("pontos", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["jogo_id"], ["jogos.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.UniqueConstraint("usuario_id", "jogo_id", name="uq_palpite_usuario_jogo"),
    )
    op.create_index(op.f("ix_palpites_jogo_id"), "palpites", ["jogo_id"], unique=False)
    op.create_index(op.f("ix_palpites_usuario_id"), "palpites", ["usuario_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_palpites_usuario_id"), table_name="palpites")
    op.drop_index(op.f("ix_palpites_jogo_id"), table_name="palpites")
    op.drop_table("palpites")

    op.drop_index(op.f("ix_jogos_rodada_id"), table_name="jogos")
    op.drop_index(op.f("ix_jogos_data_hora"), table_name="jogos")
    op.drop_table("jogos")

    op.drop_index(op.f("ix_usuarios_username"), table_name="usuarios")
    op.drop_table("usuarios")

    op.drop_index(op.f("ix_rodadas_ordem"), table_name="rodadas")
    op.drop_table("rodadas")
