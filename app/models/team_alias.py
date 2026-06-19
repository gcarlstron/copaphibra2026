"""TeamAlias model — de-para entre abreviação FIFA/ESPN e nome PT-BR.

A coluna `nome` guarda a grafia exata de `Jogo.time_casa/time_visitante`
para que o match seja feito por igualdade de string, sem normalização em
tempo de execução.
"""

from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TeamAlias(Base):
    __tablename__ = "team_alias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    abreviacao: Mapped[str] = mapped_column(
        String(10), nullable=False, unique=True, index=True
    )
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    nome_en: Mapped[str] = mapped_column(String(120), nullable=False)
    escudo_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
