from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Jogo, Palpite, Rodada, Usuario
from app.services.prazo import rodada_aberta_para_edicao
from app.services.ranking import chave_de_ranking, contar_buckets_de_pontos

# Status values used in Jogo.status (plain strings, no enum in the schema).
STATUS_ENCERRADO = "encerrado"
STATUS_AGENDADO = "agendado"
STATUS_EM_ANDAMENTO = "em_andamento"
STATUS_INTERVALO = "intervalo"

# Estados que representam um jogo "ao vivo" (bola rolando ou intervalo).
STATUS_AO_VIVO = (STATUS_EM_ANDAMENTO, STATUS_INTERVALO)

_JOGOS_RECENTES_LIMITE = 5
_PROXIMOS_JOGOS_LIMITE = 5


@dataclass(slots=True)
class ItemClassificacao:
    posicao: int
    nome: str
    total: int
    qtd_9: int
    qtd_6: int
    qtd_4: int
    qtd_3: int


@dataclass(slots=True)
class JogoResumoView:
    jogo_id: int
    data_hora: datetime
    time_casa: str
    time_visitante: str
    gols_casa: int | None
    gols_visitante: int | None
    status: str


@dataclass(slots=True)
class RodadaAbertaView:
    nome: str
    fechamento: datetime | None


@dataclass(slots=True)
class DashboardData:
    classificacao: list[ItemClassificacao]
    jogos_ao_vivo: list[JogoResumoView]
    jogos_recentes: list[JogoResumoView]
    proximos_jogos: list[JogoResumoView]
    rodadas_abertas: list[RodadaAbertaView]


def _montar_classificacao(db: Session) -> list[ItemClassificacao]:
    """Agrega pontos de cada usuário ativo e ordena pelo critério de desempate."""
    # Busca todos os usuários ativos com seleção explícita de colunas.
    stmt_usuarios = select(Usuario.id, Usuario.nome).where(Usuario.ativo == True)  # noqa: E712
    usuarios = db.execute(stmt_usuarios).all()

    if not usuarios:
        return []

    usuario_ids = [u.id for u in usuarios]

    # Busca todos os palpites com pontos dos usuários ativos.
    # Palpites com pontos == 0 e sem resultado lançado também são incluídos
    # (pontos = 0 é o default; só conta o que foi lançado).
    stmt_palpites = select(Palpite.usuario_id, Palpite.pontos).where(
        Palpite.usuario_id.in_(usuario_ids)
    )
    palpite_rows = db.execute(stmt_palpites).all()

    # Agrupa pontos por usuário.
    pontos_por_usuario: dict[int, list[int]] = {u.id: [] for u in usuarios}
    for usuario_id, pontos in palpite_rows:
        pontos_por_usuario[usuario_id].append(pontos)

    # Monta as entradas sem posição ainda, para poder ordenar depois.
    @dataclass(slots=True)
    class _EntradaTemp:
        usuario_id: int
        nome: str
        total: int
        qtd_9: int
        qtd_6: int
        qtd_4: int
        qtd_3: int

    entradas: list[_EntradaTemp] = []
    for usuario in usuarios:
        pontos_lista = pontos_por_usuario[usuario.id]
        buckets = contar_buckets_de_pontos(pontos_lista)
        total = sum(pontos_lista)
        entradas.append(
            _EntradaTemp(
                usuario_id=usuario.id,
                nome=usuario.nome,
                total=total,
                qtd_9=buckets[9],
                qtd_6=buckets[6],
                qtd_4=buckets[4],
                qtd_3=buckets[3],
            )
        )

    # Ordena pelo critério de desempate (desc: maior chave primeiro).
    entradas.sort(
        key=lambda e: chave_de_ranking(e.total, e.qtd_9, e.qtd_6, e.qtd_4, e.qtd_3),
        reverse=True,
    )

    # Atribui posições com empate estável: mesma posição para chave idêntica.
    resultado: list[ItemClassificacao] = []
    posicao_atual = 1
    for i, entrada in enumerate(entradas):
        if i > 0:
            anterior = entradas[i - 1]
            chave_atual = chave_de_ranking(entrada.total, entrada.qtd_9, entrada.qtd_6, entrada.qtd_4, entrada.qtd_3)
            chave_anterior = chave_de_ranking(anterior.total, anterior.qtd_9, anterior.qtd_6, anterior.qtd_4, anterior.qtd_3)
            if chave_atual < chave_anterior:
                posicao_atual = i + 1

        resultado.append(
            ItemClassificacao(
                posicao=posicao_atual,
                nome=entrada.nome,
                total=entrada.total,
                qtd_9=entrada.qtd_9,
                qtd_6=entrada.qtd_6,
                qtd_4=entrada.qtd_4,
                qtd_3=entrada.qtd_3,
            )
        )

    return resultado


def _montar_jogos_ao_vivo(db: Session) -> list[JogoResumoView]:
    """Retorna os jogos em andamento ou no intervalo, do mais cedo para o mais tarde."""
    stmt = (
        select(
            Jogo.id,
            Jogo.data_hora,
            Jogo.time_casa,
            Jogo.time_visitante,
            Jogo.gols_casa,
            Jogo.gols_visitante,
            Jogo.status,
        )
        .where(Jogo.status.in_(STATUS_AO_VIVO))
        .order_by(Jogo.data_hora.asc())
    )
    rows = db.execute(stmt).all()
    return [
        JogoResumoView(
            jogo_id=r.id,
            data_hora=r.data_hora,
            time_casa=r.time_casa,
            time_visitante=r.time_visitante,
            gols_casa=r.gols_casa,
            gols_visitante=r.gols_visitante,
            status=r.status,
        )
        for r in rows
    ]


def _montar_jogos_recentes(db: Session) -> list[JogoResumoView]:
    """Retorna os últimos 5 jogos encerrados, do mais recente para o mais antigo."""
    stmt = (
        select(
            Jogo.id,
            Jogo.data_hora,
            Jogo.time_casa,
            Jogo.time_visitante,
            Jogo.gols_casa,
            Jogo.gols_visitante,
            Jogo.status,
        )
        .where(Jogo.status == STATUS_ENCERRADO)
        .order_by(Jogo.data_hora.desc())
        .limit(_JOGOS_RECENTES_LIMITE)
    )
    rows = db.execute(stmt).all()
    return [
        JogoResumoView(
            jogo_id=r.id,
            data_hora=r.data_hora,
            time_casa=r.time_casa,
            time_visitante=r.time_visitante,
            gols_casa=r.gols_casa,
            gols_visitante=r.gols_visitante,
            status=r.status,
        )
        for r in rows
    ]


def _montar_proximos_jogos(db: Session) -> list[JogoResumoView]:
    """Retorna os próximos 5 jogos agendados, do mais próximo para o mais distante."""
    stmt = (
        select(
            Jogo.id,
            Jogo.data_hora,
            Jogo.time_casa,
            Jogo.time_visitante,
            Jogo.gols_casa,
            Jogo.gols_visitante,
            Jogo.status,
        )
        .where(Jogo.status == STATUS_AGENDADO)
        .order_by(Jogo.data_hora.asc())
        .limit(_PROXIMOS_JOGOS_LIMITE)
    )
    rows = db.execute(stmt).all()
    return [
        JogoResumoView(
            jogo_id=r.id,
            data_hora=r.data_hora,
            time_casa=r.time_casa,
            time_visitante=r.time_visitante,
            gols_casa=r.gols_casa,
            gols_visitante=r.gols_visitante,
            status=r.status,
        )
        for r in rows
    ]


def _montar_rodadas_abertas(db: Session, agora: datetime) -> list[RodadaAbertaView]:
    """Lista as rodadas abertas para edição neste momento."""
    stmt = select(Rodada.nome, Rodada.aberta, Rodada.abertura, Rodada.fechamento)
    rodadas = db.execute(stmt).all()
    abertas: list[RodadaAbertaView] = []
    for r in rodadas:
        if rodada_aberta_para_edicao(r.aberta, r.abertura, r.fechamento, agora):
            abertas.append(RodadaAbertaView(nome=r.nome, fechamento=r.fechamento))
    return abertas


def montar_dashboard(db: Session, agora: datetime | None = None) -> DashboardData:
    """Agrega todos os dados necessários para a tela de dashboard/classificação."""
    momento_atual = agora or datetime.now(timezone.utc)
    return DashboardData(
        classificacao=_montar_classificacao(db),
        jogos_ao_vivo=_montar_jogos_ao_vivo(db),
        jogos_recentes=_montar_jogos_recentes(db),
        proximos_jogos=_montar_proximos_jogos(db),
        rodadas_abertas=_montar_rodadas_abertas(db, momento_atual),
    )
