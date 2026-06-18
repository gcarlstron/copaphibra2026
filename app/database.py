from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _normalizar_database_url(url: str) -> str:
    """Normaliza a URL do banco para garantir o dialeto correto.

    Provedores como Neon/Render entregam URLs com prefixo ``postgres://`` ou
    ``postgresql://`` (sem driver explícito). SQLAlchemy 2.x + psycopg 3
    exige o dialeto ``postgresql+psycopg://``.

    Regras:
    - ``postgres://...``          → ``postgresql+psycopg://...``
    - ``postgresql://...``        → ``postgresql+psycopg://...``
    - ``postgresql+psycopg://...``→ inalterada
    - ``sqlite://...`` ou outra   → inalterada
    """
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


settings = get_settings()
_database_url = _normalizar_database_url(settings.database_url)

engine = create_engine(
    _database_url,
    connect_args={"check_same_thread": False}
    if _database_url.startswith("sqlite")
    else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
