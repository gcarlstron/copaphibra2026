from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Jogo, Palpite, Rodada, Usuario
from app.services.dashboard import STATUS_AGENDADO, STATUS_ENCERRADO  # noqa: F401 (re-exported for callers)
from app.services.prazo import palpites_de_terceiros_visiveis


@dataclass(slots=True)
class JogoDetalheView:
    id: int
    rodada_nome: str
    data_hora: datetime
    time_casa: str
    time_visitante: str
    gols_casa: int | None
    gols_visitante: int | None
    status: str


@dataclass(slots=True)
class PalpiteDetalheView:
    nome: str
    gols_casa: int
    gols_visitante: int
    pontos: int


@dataclass(slots=True)
class JogoDetalheData:
    jogo: JogoDetalheView
    terceiros_visiveis: bool
    palpites: list[PalpiteDetalheView]


def detalhe_do_jogo(
    db: Session,
    jogo_id: int,
    usuario: Usuario,
    agora: datetime | None = None,
) -> JogoDetalheData:
    """Retorna os dados de detalhe de um jogo para o usuário autenticado.

    Levanta ValueError se o jogo não existir (o router converte em HTTP 404).
    Regra de privacidade (CLAUDE.md regra 4): palpites de terceiros só ficam
    visíveis depois que a rodada fecha — delegado a palpites_de_terceiros_visiveis.
    """
    momento_atual = agora or datetime.now(timezone.utc)

    # Busca o jogo e a rodada com seleção explícita de colunas.
    stmt_jogo = (
        select(
            Jogo.id,
            Jogo.rodada_id,
            Jogo.data_hora,
            Jogo.time_casa,
            Jogo.time_visitante,
            Jogo.gols_casa,
            Jogo.gols_visitante,
            Jogo.status,
            Rodada.nome.label("rodada_nome"),
            Rodada.aberta,
            Rodada.abertura,
            Rodada.fechamento,
        )
        .join(Rodada, Jogo.rodada_id == Rodada.id)
        .where(Jogo.id == jogo_id)
    )
    row = db.execute(stmt_jogo).one_or_none()
    if row is None:
        raise ValueError(f"Jogo {jogo_id} não encontrado")

    jogo_view = JogoDetalheView(
        id=row.id,
        rodada_nome=row.rodada_nome,
        data_hora=row.data_hora,
        time_casa=row.time_casa,
        time_visitante=row.time_visitante,
        gols_casa=row.gols_casa,
        gols_visitante=row.gols_visitante,
        status=row.status,
    )

    terceiros_visiveis = palpites_de_terceiros_visiveis(
        row.aberta, row.abertura, row.fechamento, momento_atual
    )

    if terceiros_visiveis:
        # Todos os palpites de usuários ativos, ordenados por pontos desc.
        stmt_palpites = (
            select(
                Usuario.nome,
                Palpite.gols_casa,
                Palpite.gols_visitante,
                Palpite.pontos,
            )
            .join(Usuario, Palpite.usuario_id == Usuario.id)
            .where(
                Palpite.jogo_id == jogo_id,
                Usuario.ativo == True,  # noqa: E712
            )
            .order_by(Palpite.pontos.desc())
        )
        palpite_rows = db.execute(stmt_palpites).all()
        palpites: list[PalpiteDetalheView] = [
            PalpiteDetalheView(
                nome=r.nome,
                gols_casa=r.gols_casa,
                gols_visitante=r.gols_visitante,
                pontos=r.pontos,
            )
            for r in palpite_rows
        ]
    else:
        # Apenas o palpite do próprio usuário (ou lista vazia).
        stmt_proprio = select(
            Usuario.nome,
            Palpite.gols_casa,
            Palpite.gols_visitante,
            Palpite.pontos,
        ).join(Usuario, Palpite.usuario_id == Usuario.id).where(
            Palpite.jogo_id == jogo_id,
            Palpite.usuario_id == usuario.id,
        )
        proprio = db.execute(stmt_proprio).one_or_none()
        if proprio is None:
            palpites = []
        else:
            palpites = [
                PalpiteDetalheView(
                    nome=proprio.nome,
                    gols_casa=proprio.gols_casa,
                    gols_visitante=proprio.gols_visitante,
                    pontos=proprio.pontos,
                )
            ]

    return JogoDetalheData(
        jogo=jogo_view,
        terceiros_visiveis=terceiros_visiveis,
        palpites=palpites,
    )
