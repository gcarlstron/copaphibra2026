from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Jogo, Palpite, Rodada, Usuario
from app.models.team_alias import TeamAlias
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
    escudo_casa: str | None
    escudo_visitante: str | None


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


# ---------------------------------------------------------------------------
# 11c — Dataclasses para listagem de todos os jogos
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class JogoListaItem:
    id: int
    data_hora: datetime
    time_casa: str
    time_visitante: str
    escudo_casa: str | None
    escudo_visitante: str | None
    gols_casa: int | None
    gols_visitante: int | None
    status: str
    meus_pontos: int | None


@dataclass(slots=True)
class RodadaGrupo:
    rodada_nome: str
    ordem: int
    jogos: list[JogoListaItem]


@dataclass(slots=True)
class JogosListaData:
    grupos: list[RodadaGrupo]


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
    Fase 11b: inclui escudo_casa e escudo_visitante via lookup em team_alias.
    """
    momento_atual = agora or datetime.now(timezone.utc)

    # Alias para o LEFT JOIN duplo em team_alias (casa e visitante).
    ta_casa = TeamAlias.__table__.alias("ta_casa")
    ta_vis = TeamAlias.__table__.alias("ta_vis")

    # Busca o jogo, a rodada e os escudos com seleção explícita de colunas.
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
            ta_casa.c.escudo_url.label("escudo_casa"),
            ta_vis.c.escudo_url.label("escudo_visitante"),
        )
        .join(Rodada, Jogo.rodada_id == Rodada.id)
        .outerjoin(ta_casa, Jogo.time_casa == ta_casa.c.nome)
        .outerjoin(ta_vis, Jogo.time_visitante == ta_vis.c.nome)
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
        escudo_casa=row.escudo_casa,
        escudo_visitante=row.escudo_visitante,
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


def listar_todos_os_jogos(db: Session, usuario: Usuario) -> JogosListaData:
    """Retorna todos os jogos agrupados por rodada (ordem asc), jogos por data_hora.

    Cada item inclui:
    - times + escudos (LEFT JOIN em team_alias para casa e visitante)
    - placar/status
    - meus_pontos: Palpite.pontos do próprio usuário naquele jogo, ou None

    Privacidade: nunca carrega palpites/pontos de terceiros — só do próprio usuário.
    Performance: 1 query de jogos+rodada+escudos; 1 query dos palpites do usuário
                 (mapa jogo_id→pontos). Sem N+1.
    """
    ta_casa = TeamAlias.__table__.alias("ta_casa")
    ta_vis = TeamAlias.__table__.alias("ta_vis")

    # Query 1: todos os jogos com rodada + escudos — ordenados por rodada.ordem, data_hora.
    stmt_jogos = (
        select(
            Jogo.id,
            Jogo.data_hora,
            Jogo.time_casa,
            Jogo.time_visitante,
            Jogo.gols_casa,
            Jogo.gols_visitante,
            Jogo.status,
            Rodada.id.label("rodada_id"),
            Rodada.nome.label("rodada_nome"),
            Rodada.ordem,
            ta_casa.c.escudo_url.label("escudo_casa"),
            ta_vis.c.escudo_url.label("escudo_visitante"),
        )
        .join(Rodada, Jogo.rodada_id == Rodada.id)
        .outerjoin(ta_casa, Jogo.time_casa == ta_casa.c.nome)
        .outerjoin(ta_vis, Jogo.time_visitante == ta_vis.c.nome)
        .order_by(Rodada.ordem.asc(), Jogo.data_hora.asc())
    )
    jogo_rows = db.execute(stmt_jogos).all()

    # Query 2: todos os palpites do próprio usuário → mapa jogo_id → pontos.
    stmt_palpites = select(
        Palpite.jogo_id,
        Palpite.pontos,
    ).where(Palpite.usuario_id == usuario.id)
    meus_pontos_map: dict[int, int] = {
        r.jogo_id: r.pontos for r in db.execute(stmt_palpites).all()
    }

    # Monta os grupos por rodada preservando a ordem da query.
    grupos: dict[int, RodadaGrupo] = {}  # rodada_id → RodadaGrupo
    for r in jogo_rows:
        if r.rodada_id not in grupos:
            grupos[r.rodada_id] = RodadaGrupo(
                rodada_nome=r.rodada_nome,
                ordem=r.ordem,
                jogos=[],
            )
        item = JogoListaItem(
            id=r.id,
            data_hora=r.data_hora,
            time_casa=r.time_casa,
            time_visitante=r.time_visitante,
            escudo_casa=r.escudo_casa,
            escudo_visitante=r.escudo_visitante,
            gols_casa=r.gols_casa,
            gols_visitante=r.gols_visitante,
            status=r.status,
            meus_pontos=meus_pontos_map.get(r.id),
        )
        grupos[r.rodada_id].jogos.append(item)

    return JogosListaData(grupos=list(grupos.values()))
