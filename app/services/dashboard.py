from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Jogo, Palpite, Rodada, Usuario
from app.models.sync_state import SyncState
from app.services.prazo import rodada_aberta_para_edicao
from app.services.ranking import chave_de_ranking, contar_buckets_de_pontos
from app.services.tempo import agora as agora_dados

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
    # Última sincronização de resultados com a ESPN (None se nunca rodou).
    ultima_sync: datetime | None = None
    # Texto relativo amigável da última sync (ex.: "há 3 min"); None se nunca rodou.
    ultima_sync_texto: str | None = None


def _rodadas_abertas_para_edicao_ids(db: Session, agora: datetime) -> set[int]:
    """IDs das rodadas abertas para edição AGORA (palpites ainda em sigilo)."""
    stmt = select(Rodada.id, Rodada.aberta, Rodada.abertura, Rodada.fechamento)
    return {
        r.id
        for r in db.execute(stmt).all()
        if rodada_aberta_para_edicao(r.aberta, r.abertura, r.fechamento, agora)
    }


def _montar_classificacao(db: Session, agora: datetime) -> list[ItemClassificacao]:
    """Agrega pontos de cada usuário ativo e ordena pelo critério de desempate.

    Privacidade (Regra #4): pontos de jogos cuja rodada ainda está ABERTA para
    edição não entram na soma. Caso contrário, um jogo encerrado dentro de uma
    rodada ainda aberta (lançar resultado encerra o jogo mas não a rodada —
    decisão D3) faria o total/buckets revelarem que o jogador pontuou antes de a
    rodada fechar. No fluxo normal isto é um no-op: palpites de rodada aberta
    valem 0 (sem resultado lançado) e não afetam total nem buckets.
    """
    # Busca todos os usuários ativos com seleção explícita de colunas.
    stmt_usuarios = select(Usuario.id, Usuario.nome).where(Usuario.ativo == True)  # noqa: E712
    usuarios = db.execute(stmt_usuarios).all()

    if not usuarios:
        return []

    usuario_ids = [u.id for u in usuarios]
    rodadas_abertas = _rodadas_abertas_para_edicao_ids(db, agora)

    # Busca os palpites dos usuários ativos junto com a rodada do jogo, para
    # excluir os de rodadas ainda abertas para edição (ver docstring).
    stmt_palpites = (
        select(Palpite.usuario_id, Palpite.pontos, Jogo.rodada_id)
        .join(Jogo, Palpite.jogo_id == Jogo.id)
        .where(Palpite.usuario_id.in_(usuario_ids))
    )
    palpite_rows = db.execute(stmt_palpites).all()

    # Agrupa pontos por usuário, ignorando rodadas ainda abertas para edição.
    pontos_por_usuario: dict[int, list[int]] = {u.id: [] for u in usuarios}
    for row in palpite_rows:
        if row.rodada_id in rodadas_abertas:
            continue
        pontos_por_usuario[row.usuario_id].append(row.pontos)

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


def _obter_ultima_sync(db: Session) -> datetime | None:
    """Lê o timestamp da última sincronização de resultados ESPN (SyncState)."""
    # Import adiado: evita ciclo (sync_resultados importa STATUS_ENCERRADO daqui).
    from app.services.sync_resultados import CHAVE_SYNC

    return db.scalar(
        select(SyncState.ultima_execucao).where(SyncState.chave == CHAVE_SYNC)
    )


def _descrever_ultima_sync(quando: datetime | None, agora: datetime) -> str | None:
    """Descreve, de forma relativa e amigável, quando foi a última sincronização.

    Ex.: "agora mesmo", "há 3 min", "há 2 h", "há 5 d". Retorna None se nunca rodou.
    Normaliza valores naive para UTC (o SQLite devolve datetimes sem tzinfo).
    """
    if quando is None:
        return None

    q = quando if quando.tzinfo is not None else quando.replace(tzinfo=timezone.utc)
    a = agora if agora.tzinfo is not None else agora.replace(tzinfo=timezone.utc)

    segundos = (a - q).total_seconds()
    if segundos < 0:
        segundos = 0
    if segundos < 60:
        return "agora mesmo"

    minutos = int(segundos // 60)
    if minutos < 60:
        return f"há {minutos} min"

    horas = minutos // 60
    if horas < 24:
        return f"há {horas} h"

    dias = horas // 24
    return f"há {dias} d"


def montar_dashboard(db: Session, agora: datetime | None = None) -> DashboardData:
    """Agrega todos os dados necessários para a tela de dashboard/classificação."""
    momento_atual = agora or agora_dados()
    ultima_sync = _obter_ultima_sync(db)
    return DashboardData(
        classificacao=_montar_classificacao(db, momento_atual),
        jogos_ao_vivo=_montar_jogos_ao_vivo(db),
        jogos_recentes=_montar_jogos_recentes(db),
        proximos_jogos=_montar_proximos_jogos(db),
        rodadas_abertas=_montar_rodadas_abertas(db, momento_atual),
        ultima_sync=ultima_sync,
        ultima_sync_texto=_descrever_ultima_sync(ultima_sync, momento_atual),
    )
