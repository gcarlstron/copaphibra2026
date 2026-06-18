from __future__ import annotations

from datetime import datetime
from datetime import timezone

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Palpite(Base):
    __tablename__ = "palpites"
    __table_args__ = (UniqueConstraint("usuario_id", "jogo_id", name="uq_palpite_usuario_jogo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    jogo_id: Mapped[int] = mapped_column(ForeignKey("jogos.id"), nullable=False, index=True)
    gols_casa: Mapped[int] = mapped_column(Integer, nullable=False)
    gols_visitante: Mapped[int] = mapped_column(Integer, nullable=False)
    pontos: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    usuario: Mapped["Usuario"] = relationship(back_populates="palpites")
    jogo: Mapped["Jogo"] = relationship(back_populates="palpites")
