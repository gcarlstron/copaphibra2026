"""SyncState model — persiste o timestamp da última sincronização.

Usado para throttle do sync de resultados ESPN: evita chamadas repetidas em
logins simultâneos (Render free reinicia → nada em memória).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SyncState(Base):
    __tablename__ = "sync_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chave: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    ultima_execucao: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
