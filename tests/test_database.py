from __future__ import annotations

"""Testes da função _normalizar_database_url em app/database.py.

Cobre os quatro casos relevantes para o deploy Postgres (Neon/Render)
sem exigir um servidor de banco real.
"""

import pytest

from app.database import _normalizar_database_url


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        # URLs Postgres sem driver explícito — devem receber +psycopg
        (
            "postgres://user:pass@host/db",
            "postgresql+psycopg://user:pass@host/db",
        ),
        (
            "postgresql://user:pass@host/db",
            "postgresql+psycopg://user:pass@host/db",
        ),
        # URL Neon típica com query params
        (
            "postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require",
            "postgresql+psycopg://user:pass@ep-xxx.neon.tech/neondb?sslmode=require",
        ),
        (
            "postgres://user:pass@ep-xxx.neon.tech/neondb?sslmode=require",
            "postgresql+psycopg://user:pass@ep-xxx.neon.tech/neondb?sslmode=require",
        ),
        # SQLite — deve ficar inalterado
        (
            "sqlite:///./copa_phibra.db",
            "sqlite:///./copa_phibra.db",
        ),
        (
            "sqlite:///:memory:",
            "sqlite:///:memory:",
        ),
        # Já com +psycopg — deve ficar inalterado (idempotente)
        (
            "postgresql+psycopg://user:pass@host/db",
            "postgresql+psycopg://user:pass@host/db",
        ),
    ],
)
def test_normalizar_database_url(entrada: str, esperado: str) -> None:
    assert _normalizar_database_url(entrada) == esperado


def test_normalizar_nao_altera_outros_drivers() -> None:
    """URLs com outros drivers (ex.: psycopg2) não devem ser alteradas."""
    url = "postgresql+psycopg2://user:pass@host/db"
    assert _normalizar_database_url(url) == url
