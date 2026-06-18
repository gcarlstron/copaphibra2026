from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Rodada(Base):
    __tablename__ = "rodadas"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    ordem: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    aberta: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    abertura: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fechamento: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    jogos: Mapped[list["Jogo"]] = relationship(back_populates="rodada")
