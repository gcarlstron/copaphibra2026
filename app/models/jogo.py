from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Jogo(Base):
    __tablename__ = "jogos"
    __table_args__ = (
        UniqueConstraint(
            "rodada_id", "time_casa", "time_visitante", name="uq_jogo_rodada_times"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    rodada_id: Mapped[int] = mapped_column(ForeignKey("rodadas.id"), nullable=False, index=True)
    # Identificador estável do evento na ESPN (ex.: "760486"). Usado no mata-mata
    # para fazer get-or-create por ID em vez de por par de times, permitindo
    # atualização in-place quando um placeholder se torna um time real.
    # NULL para jogos da fase de grupos (importados da planilha sem ESPN ID).
    # Múltiplos NULL não violam a constraint UNIQUE no SQLite nem no Postgres.
    espn_event_id: Mapped[str | None] = mapped_column(
        String(32), nullable=True, unique=True, index=True
    )
    data_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    time_casa: Mapped[str] = mapped_column(String(120), nullable=False)
    time_visitante: Mapped[str] = mapped_column(String(120), nullable=False)
    gols_casa: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gols_visitante: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="agendado", nullable=False)

    rodada: Mapped["Rodada"] = relationship(back_populates="jogos")
    palpites: Mapped[list["Palpite"]] = relationship(back_populates="jogo")
