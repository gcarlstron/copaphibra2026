from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Jogo(Base):
    __tablename__ = "jogos"

    id: Mapped[int] = mapped_column(primary_key=True)
    rodada_id: Mapped[int] = mapped_column(ForeignKey("rodadas.id"), nullable=False, index=True)
    data_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    time_casa: Mapped[str] = mapped_column(String(120), nullable=False)
    time_visitante: Mapped[str] = mapped_column(String(120), nullable=False)
    gols_casa: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gols_visitante: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="agendado", nullable=False)

    rodada: Mapped["Rodada"] = relationship(back_populates="jogos")
    palpites: Mapped[list["Palpite"]] = relationship(back_populates="jogo")
