from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models import Jogo, Palpite, Rodada, Usuario
from app.services.prazo import palpites_de_terceiros_visiveis, rodada_aberta_para_edicao


@dataclass(slots=True)
class JogoPalpiteView:
    jogo_id: int
    data_hora: datetime
    time_casa: str
    time_visitante: str
    gols_casa: int | None
    gols_visitante: int | None
    palpite_casa: int | None
    palpite_visitante: int | None
    aberta_para_edicao: bool
    terceiros_visiveis: bool


@dataclass(slots=True)
class RodadaPalpitesView:
    rodada_id: int
    rodada_nome: str
    ordem: int
    aberta_para_edicao: bool
    terceiros_visiveis: bool
    jogos: list[JogoPalpiteView]


def listar_palpites_do_usuario(db: Session, usuario: Usuario, agora: datetime | None = None) -> list[RodadaPalpitesView]:
    momento_atual = agora or datetime.now(timezone.utc)
    stmt = (
        select(Jogo, Rodada, Palpite)
        .join(Rodada, Jogo.rodada_id == Rodada.id)
        .outerjoin(
            Palpite,
            and_(Palpite.jogo_id == Jogo.id, Palpite.usuario_id == usuario.id),
        )
        .order_by(Rodada.ordem, Jogo.data_hora)
    )

    rows = db.execute(stmt).all()
    agrupado: dict[int, RodadaPalpitesView] = {}

    for jogo, rodada, palpite in rows:
        aberta_para_edicao = rodada_aberta_para_edicao(rodada.aberta, rodada.abertura, rodada.fechamento, momento_atual)
        terceiros_visiveis = palpites_de_terceiros_visiveis(
            rodada.aberta, rodada.abertura, rodada.fechamento, momento_atual
        )

        rodada_view = agrupado.get(rodada.id)
        if rodada_view is None:
            rodada_view = RodadaPalpitesView(
                rodada_id=rodada.id,
                rodada_nome=rodada.nome,
                ordem=rodada.ordem,
                aberta_para_edicao=aberta_para_edicao,
                terceiros_visiveis=terceiros_visiveis,
                jogos=[],
            )
            agrupado[rodada.id] = rodada_view

        rodada_view.jogos.append(
            JogoPalpiteView(
                jogo_id=jogo.id,
                data_hora=jogo.data_hora,
                time_casa=jogo.time_casa,
                time_visitante=jogo.time_visitante,
                gols_casa=jogo.gols_casa,
                gols_visitante=jogo.gols_visitante,
                palpite_casa=None if palpite is None else palpite.gols_casa,
                palpite_visitante=None if palpite is None else palpite.gols_visitante,
                aberta_para_edicao=aberta_para_edicao,
                terceiros_visiveis=terceiros_visiveis,
            )
        )

    return list(agrupado.values())


def salvar_palpite(
    db: Session,
    usuario: Usuario,
    jogo_id: int,
    gols_casa: int,
    gols_visitante: int,
    agora: datetime | None = None,
) -> Palpite:
    momento_atual = agora or datetime.now(timezone.utc)

    if gols_casa < 0 or gols_visitante < 0:
        raise ValueError("Placar inválido: gols não podem ser negativos")

    jogo_stmt = select(Jogo, Rodada).join(Rodada, Jogo.rodada_id == Rodada.id).where(Jogo.id == jogo_id)
    result = db.execute(jogo_stmt).one_or_none()
    if result is None:
        raise LookupError("Jogo não encontrado")

    jogo, rodada = result
    if not rodada_aberta_para_edicao(rodada.aberta, rodada.abertura, rodada.fechamento, momento_atual):
        raise PermissionError("Rodada fechada para edição")

    palpite_stmt = select(Palpite).where(Palpite.usuario_id == usuario.id, Palpite.jogo_id == jogo.id)
    palpite = db.scalar(palpite_stmt)
    if palpite is None:
        palpite = Palpite(
            usuario_id=usuario.id,
            jogo_id=jogo.id,
            gols_casa=gols_casa,
            gols_visitante=gols_visitante,
        )
        db.add(palpite)
    else:
        palpite.gols_casa = gols_casa
        palpite.gols_visitante = gols_visitante

    db.commit()
    db.refresh(palpite)
    return palpite
