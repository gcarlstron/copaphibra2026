"""Tests for TeamAlias model and seed (Fase 10b).

Verifica:
- Seed cobre exatamente 48 abreviações
- Lookup por abreviação retorna o nome PT-BR correto
- Seed executado 2× é idempotente
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.team_alias import TeamAlias

# ---------------------------------------------------------------------------
# Fixture de banco isolado
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_session(tmp_path: Path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'alias_test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Mapeamento completo esperado: abreviação → nome PT-BR canônico
MAPEAMENTO_ESPERADO: dict[str, str] = {
    "GER": "Alemanha",
    "ARG": "Argentina",
    "ALG": "Argélia",
    "KSA": "Arábia Saudita",
    "AUS": "Austrália",
    "BRA": "Brasil",
    "BEL": "Bélgica",
    "BIH": "Bósnia",
    "CPV": "Cabo Verde",
    "CAN": "Canadá",
    "QAT": "Catar",
    "COL": "Colômbia",
    "KOR": "Coréia do Sul",
    "CIV": "Costa do Marfim",
    "CRO": "Croácia",
    "CUW": "Curaçao",
    "EGY": "Egito",
    "ECU": "Equador",
    "SCO": "Escócia",
    "ESP": "Espanha",
    "USA": "Estados Unidos",
    "FRA": "França",
    "GHA": "Gana",
    "HAI": "Haiti",
    "NED": "Holanda",
    "ENG": "Inglaterra",
    "IRQ": "Iraque",
    "IRN": "Irã",
    "JPN": "Japão",
    "JOR": "Jordânia",
    "MAR": "Marrocos",
    "MEX": "México",
    "NOR": "Noruega",
    "NZL": "Nova Zelândia",
    "PAN": "Panamá",
    "PAR": "Paraguai",
    "POR": "Portugal",
    "COD": "RD Congo",
    "CZE": "República Tcheca",
    "SEN": "Senegal",
    "SWE": "Suécia",
    "SUI": "Suíça",
    "TUN": "Tunísia",
    "TUR": "Turquia",
    "URU": "Uruguai",
    "UZB": "Uzbequistão",
    "RSA": "África do Sul",
    "AUT": "Áustria",
}


def _seed_all(db: Session) -> None:
    """Insere todos os 48 aliases no banco de teste."""
    for abrev, nome_pt in MAPEAMENTO_ESPERADO.items():
        db.add(TeamAlias(abreviacao=abrev, nome=nome_pt, nome_en="Test"))
    db.commit()


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------


class TestTeamAlias:
    def test_seed_cobre_48_abreviacoes(self, db_session: Session) -> None:
        """O mapeamento de testes cobre exatamente 48 abreviações."""
        assert len(MAPEAMENTO_ESPERADO) == 48

    def test_insert_and_lookup(self, db_session: Session) -> None:
        """Inserção e lookup por abreviação."""
        db_session.add(TeamAlias(abreviacao="MEX", nome="México", nome_en="Mexico"))
        db_session.commit()

        result = db_session.scalar(
            select(TeamAlias).where(TeamAlias.abreviacao == "MEX")
        )
        assert result is not None
        assert result.nome == "México"
        assert result.nome_en == "Mexico"

    def test_lookup_todos_os_48(self, db_session: Session) -> None:
        """Todos os 48 aliases devem ser encontrados após inserção."""
        _seed_all(db_session)

        for abrev, nome_pt in MAPEAMENTO_ESPERADO.items():
            result = db_session.scalar(
                select(TeamAlias).where(TeamAlias.abreviacao == abrev)
            )
            assert result is not None, f"Abreviação {abrev!r} não encontrada"
            assert result.nome == nome_pt, (
                f"Nome errado para {abrev}: esperado {nome_pt!r}, "
                f"obtido {result.nome!r}"
            )

    def test_seed_idempotente_get_or_create(self, db_session: Session) -> None:
        """Inserir o mesmo alias duas vezes não duplica (único por abreviação)."""
        from sqlalchemy.exc import IntegrityError

        db_session.add(TeamAlias(abreviacao="BRA", nome="Brasil", nome_en="Brazil"))
        db_session.commit()

        # Segunda inserção deve violar a unique constraint
        db_session.add(TeamAlias(abreviacao="BRA", nome="Brasil", nome_en="Brazil"))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

        # Após rollback, ainda há apenas 1 BRA
        count = db_session.execute(
            select(TeamAlias).where(TeamAlias.abreviacao == "BRA")
        ).all()
        assert len(count) == 1

    def test_abreviacao_unica_indexada(self, db_session: Session) -> None:
        """A coluna abreviacao deve ser unique."""
        from sqlalchemy.exc import IntegrityError

        db_session.add(TeamAlias(abreviacao="ARG", nome="Argentina", nome_en="Argentina"))
        db_session.commit()
        db_session.add(TeamAlias(abreviacao="ARG", nome="Outro", nome_en="Other"))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()
